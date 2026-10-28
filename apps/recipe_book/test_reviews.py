import json
from datetime import timedelta
from io import BytesIO, StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.catalog.recipe_images import recipe_images_for

from . import tests as cooking_tests
from .admin import RecipeReviewAdmin
from .models import CookingHistory, RecipePhotoCleanup, RecipeReview, ReviewQuota
from .reviews import (
    ReviewLimited,
    attach_review_photo,
    normalize_review_photo,
    public_username,
    review_context,
    review_photo_url,
)
from .services import cook
from .views import recipe_review_photo_file


class MemoryPhotoStorage:
    def __init__(self):
        self.files = {}
        self.fail_deleting = set()

    def save(self, name, content):
        self.files[name] = content.read()
        return name

    def delete(self, name):
        if name in self.fail_deleting:
            raise OSError("temporary storage outage")
        self.files.pop(name, None)


def jpeg_upload(width=2, height=2):
    output = BytesIO()
    Image.new("RGB", (width, height), "red").save(output, format="JPEG")
    return SimpleUploadedFile("review.jpg", output.getvalue(), content_type="image/jpeg")


class ReviewTests(TestCase):
    setUp = cooking_tests.CookingTests.setUp
    batch = cooking_tests.CookingTests.batch
    slot = cooking_tests.CookingTests.slot

    def post_review(self, **changes):
        payload = {"recipe_code": self.recipe.pk, "rating": 5, "comment": "Enak!", **changes}
        return self.client.post(
            reverse("modul4-review"), json.dumps(payload), content_type="application/json"
        )

    def cooked(self):
        self.batch()
        return cook(self.user, self.payload)

    def test_review_pagination_keeps_slot(self):
        for index in range(6):
            reviewer = get_user_model().objects.create_user(f"reviewer{index}")
            RecipeReview.objects.create(user=reviewer, recipe=self.recipe, rating=5)
        slot = self.slot()
        response = self.client.get(reverse("modul4"), {"recipe": self.recipe.pk, "slot": slot.pk})
        self.assertRegex(
            response.content.decode(),
            rf'href="\?[^"]*slot={slot.pk}[^"]*review_page=2#recipe-reviews"',
        )

    def test_empty_results_still_render_shared_csrf_token(self):
        response = self.client.get(reverse("modul4"), {"q": "no-such-recipe"})

        self.assertNotContains(response, 'id="recipe-detail"')
        self.assertContains(response, 'id="csrf-bootstrap"')
    def test_must_have_own_cooking_history_on_every_save(self):
        self.assertEqual(self.post_review().status_code, 403)
        self.cooked()
        self.assertEqual(self.post_review().status_code, 200)
        CookingHistory.objects.filter(user=self.user).delete()
        self.assertEqual(self.post_review(version=1, rating=3).status_code, 403)
        self.assertEqual(RecipeReview.objects.get().rating, 5)

    def test_other_users_history_does_not_qualify(self):
        self.cooked()
        self.client.force_login(self.other)
        self.assertEqual(self.post_review().status_code, 403)
        self.assertFalse(RecipeReview.objects.exists())

    def test_create_update_delete_and_stale_missing_version(self):
        self.cooked()
        self.assertEqual(self.post_review().status_code, 200)
        self.assertEqual(self.post_review().status_code, 409)
        self.assertEqual(self.post_review(version=1, rating=4).status_code, 200)
        self.assertEqual(RecipeReview.objects.get().version, 2)
        self.assertEqual(self.post_review(version=1, action="delete").status_code, 409)
        self.assertEqual(self.post_review(version=2, action="delete").status_code, 200)
        self.assertFalse(RecipeReview.objects.exists())

    def test_delete_cannot_target_another_user_and_ignores_client_user_id(self):
        self.cooked()
        self.post_review()
        self.client.force_login(self.other)
        self.assertEqual(self.post_review(action="delete", user_id=self.user.pk).status_code, 404)
        self.assertTrue(RecipeReview.objects.filter(user=self.user).exists())

    def test_photo_delete_revokes_consent_but_preserves_written_review(self):
        self.cooked()
        self.post_review()
        review = RecipeReview.objects.get(user=self.user, recipe=self.recipe)
        review.photo = "reviews/test/photo.jpg"
        review.photo_permission_granted = True
        review.photo_consent_at = timezone.now()
        review.photo_is_hidden = False
        review.version = 2
        review.save()

        url = reverse("modul4-review-photo-delete")
        stale = self.client.post(
            url,
            json.dumps({"recipe_code": self.recipe.pk, "version": 0}),
            content_type="application/json",
        )
        self.assertEqual(stale.status_code, 400)
        stale = self.client.post(
            url,
            json.dumps({"recipe_code": self.recipe.pk, "version": 1}),
            content_type="application/json",
        )
        self.assertEqual(stale.status_code, 409)

        response = self.client.post(
            url,
            json.dumps({"recipe_code": self.recipe.pk, "version": review.version}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        review.refresh_from_db()
        self.assertFalse(review.photo)
        self.assertFalse(review.photo_permission_granted)
        self.assertIsNone(review.photo_consent_at)
        self.assertTrue(review.photo_is_hidden)
        self.assertEqual(review.comment, "Enak!")
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.version, 3)

    def test_old_photo_cleanup_failure_keeps_replacement_and_can_be_retried(self):
        self.cooked()
        self.post_review()
        review = RecipeReview.objects.get(user=self.user, recipe=self.recipe)
        review.photo = "recipe-reviews/old.jpg"
        review.save(update_fields=["photo"])
        storage = MemoryPhotoStorage()
        storage.files[review.photo.name] = b"old photo"
        storage.fail_deleting.add(review.photo.name)

        with patch("apps.recipe_book.photo_storage.default_storage", storage):
            with self.captureOnCommitCallbacks(execute=True):
                result = attach_review_photo(
                    self.user,
                    self.recipe.pk,
                    review.version,
                    jpeg_upload(),
                    permission_granted=True,
                )

            review.refresh_from_db()
            self.assertEqual(result["version"], review.version)
            self.assertIn(review.photo.name, storage.files)
            cleanup = RecipePhotoCleanup.objects.get(storage_name="recipe-reviews/old.jpg")
            self.assertEqual(cleanup.attempts, 1)

            storage.fail_deleting.clear()
            call_command("cleanup_recipe_review_photos")

        self.assertFalse(RecipePhotoCleanup.objects.exists())
        self.assertNotIn("recipe-reviews/old.jpg", storage.files)

    def test_photo_cleanup_covers_account_cascade_and_retries_storage_failure(self):
        review = RecipeReview.objects.create(
            user=self.user,
            recipe=self.recipe,
            rating=5,
            photo="recipe-reviews/account-photo.jpg",
        )
        storage = MemoryPhotoStorage()
        storage.files[review.photo.name] = b"photo"
        storage.fail_deleting.add(review.photo.name)

        with patch("apps.recipe_book.photo_storage.default_storage", storage):
            with self.captureOnCommitCallbacks(execute=True):
                self.user.delete()

            self.assertFalse(RecipeReview.objects.filter(pk=review.pk).exists())
            cleanup = RecipePhotoCleanup.objects.get(storage_name="recipe-reviews/account-photo.jpg")
            self.assertEqual(cleanup.attempts, 1)

            storage.fail_deleting.clear()
            call_command("cleanup_recipe_review_photos")

        self.assertFalse(RecipePhotoCleanup.objects.exists())
        self.assertNotIn("recipe-reviews/account-photo.jpg", storage.files)

    def test_photo_upload_moderation_versions_access_and_missing_storage_file(self):
        self.cooked()
        self.post_review()
        review = RecipeReview.objects.get(user=self.user, recipe=self.recipe)
        upload_url = reverse("modul4-review-photo-upload")
        photo_url = reverse("modul4-review-photo", args=[review.pk])

        def photo_response(user, version=None):
            url = photo_url if version is None else f"{photo_url}?v={version}"
            request = RequestFactory().get(url)
            request.user = user
            return recipe_review_photo_file(request, review.pk)

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            denied = self.client.post(upload_url, {
                "recipe_code": self.recipe.pk,
                "version": review.version,
                "photo": jpeg_upload(),
            })
            self.assertEqual(denied.status_code, 400)

            uploaded = self.client.post(upload_url, {
                "recipe_code": self.recipe.pk,
                "version": review.version,
                "photo_permission": "on",
                "photo": jpeg_upload(),
            })
            self.assertEqual(uploaded.status_code, 200)
            review.refresh_from_db()
            self.assertTrue(review.photo_permission_granted)
            self.assertTrue(review.photo_is_hidden)
            self.assertEqual(review.version, 2)
            self.assertTrue(review.photo.storage.exists(review.photo.name))
            pending_url = review_photo_url(review)
            self.assertTrue(pending_url.endswith("?v=2"))
            anonymous_response = photo_response(AnonymousUser())
            self.assertEqual(anonymous_response.status_code, 302)
            owner_response = photo_response(self.user)
            self.assertEqual(owner_response.status_code, 200)
            self.assertEqual(owner_response["Cache-Control"], "private, no-store")
            owner_response.file_to_stream.close()

            other_response = photo_response(self.other)
            self.assertEqual(other_response.status_code, 404)

            # An inconsistent visible flag alone must not publish or cache a
            # photo until the moderator approval timestamp is present.
            review.photo_is_hidden = False
            review.save(update_fields=["photo_is_hidden"])
            inconsistent_owner_response = photo_response(self.user)
            self.assertEqual(
                inconsistent_owner_response["Cache-Control"], "private, no-store"
            )
            inconsistent_owner_response.file_to_stream.close()
            self.assertEqual(photo_response(self.other).status_code, 404)
            review.photo_is_hidden = True
            review.save(update_fields=["photo_is_hidden"])

            staff = get_user_model().objects.create_user("moderator", is_staff=True)
            request = RequestFactory().post("/admin/")
            request.user = staff
            model_admin = RecipeReviewAdmin(RecipeReview, admin.site)
            selected = RecipeReview.objects.filter(pk=review.pk)
            model_admin.approve_consented_photos(request, selected)
            review.refresh_from_db()
            self.assertFalse(review.photo_is_hidden)
            self.assertEqual(review.version, 3)
            approved_url = review_photo_url(review)
            self.assertTrue(approved_url.endswith("?v=3"))
            self.assertNotEqual(pending_url, approved_url)
            stale_response = photo_response(self.other, version=2)
            self.assertEqual(stale_response.status_code, 404)
            self.assertEqual(stale_response["Cache-Control"], "private, no-store")
            public_response = photo_response(self.other)
            self.assertEqual(public_response.status_code, 200)
            self.assertEqual(public_response["Cache-Control"], "private, max-age=3600")
            public_response.file_to_stream.close()
            context = review_context(self.other, self.recipe)
            self.assertEqual(context["reviews"][0].photo_url, approved_url)
            self.assertEqual(
                recipe_images_for([self.recipe.pk])[self.recipe.pk]["image_url"],
                approved_url,
            )

            self.assertEqual(self.post_review(version=2).status_code, 409)
            model_admin.hide_selected_photos(
                request, RecipeReview.objects.filter(pk=review.pk)
            )
            review.refresh_from_db()
            self.assertTrue(review.photo_is_hidden)
            self.assertEqual(review.version, 4)
            self.assertNotEqual(approved_url, review_photo_url(review))
            stale_approved_response = photo_response(self.other, version=3)
            self.assertEqual(stale_approved_response.status_code, 404)
            self.assertEqual(stale_approved_response["Cache-Control"], "private, no-store")
            self.assertFalse(
                hasattr(review_context(self.other, self.recipe)["reviews"][0], "photo_url")
            )
            self.assertNotIn(self.recipe.pk, recipe_images_for([self.recipe.pk]))
            hidden_response = photo_response(self.user)
            self.assertEqual(hidden_response.status_code, 200)
            self.assertEqual(hidden_response["Cache-Control"], "private, no-store")
            hidden_response.file_to_stream.close()

            review.photo.storage.delete(review.photo.name)
            with self.assertLogs("apps.recipe_book.views", level="WARNING") as logs:
                missing_response = photo_response(self.user)
                self.assertEqual(missing_response.status_code, 404)
            self.assertIn("review_id=", logs.output[0])

    def test_photo_upload_rejects_invalid_format_and_file_over_limit(self):
        self.cooked()
        self.post_review()
        review = RecipeReview.objects.get(user=self.user, recipe=self.recipe)
        url = reverse("modul4-review-photo-upload")

        invalid = self.client.post(url, {
            "recipe_code": self.recipe.pk,
            "version": review.version,
            "photo_permission": "on",
            "photo": SimpleUploadedFile("fake.jpg", b"not an image", content_type="image/jpeg"),
        })
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("valid", invalid.json()["error"].lower())

        too_large = self.client.post(url, {
            "recipe_code": self.recipe.pk,
            "version": review.version,
            "photo_permission": "on",
            "photo": SimpleUploadedFile(
                "large.jpg", b"x" * (6 * 1024 * 1024 + 1), content_type="image/jpeg"
            ),
        })
        self.assertEqual(too_large.status_code, 400)
        self.assertIn("6 MB", too_large.json()["error"])

        request_too_large = self.client.post(url, {
            "recipe_code": self.recipe.pk,
            "version": review.version,
            "photo_permission": "on",
            "photo": SimpleUploadedFile(
                "request-too-large.jpg", b"x" * (7 * 1024 * 1024), content_type="image/jpeg"
            ),
        })
        self.assertEqual(request_too_large.status_code, 413)
        review.refresh_from_db()
        self.assertFalse(review.photo)

    def test_photo_upload_endpoint_requires_login_history_review_and_valid_method(self):
        upload_url = reverse("modul4-review-photo-upload")
        anonymous = Client()
        self.assertEqual(anonymous.post(upload_url).status_code, 302)
        self.assertEqual(self.client.get(upload_url).status_code, 405)

        self.cooked()
        response = self.client.post(upload_url, {
            "recipe_code": self.recipe.pk,
            "version": 1,
            "photo_permission": "on",
            "photo": jpeg_upload(),
        })
        self.assertEqual(response.status_code, 404)

        self.post_review()
        self.client.force_login(self.other)
        response = self.client.post(upload_url, {
            "recipe_code": self.recipe.pk,
            "version": 1,
            "photo_permission": "on",
            "photo": jpeg_upload(),
        })
        self.assertEqual(response.status_code, 404)

    def test_upload_storage_failure_does_not_attach_or_leave_review_photo(self):
        self.cooked()
        self.post_review()
        review = RecipeReview.objects.get(user=self.user, recipe=self.recipe)
        with patch("apps.recipe_book.photo_storage.default_storage") as storage:
            storage.save.side_effect = OSError("storage unavailable")
            with self.assertRaises(OSError):
                attach_review_photo(
                    self.user, self.recipe.pk, review.version, jpeg_upload(),
                    permission_granted=True,
                )
        review.refresh_from_db()
        self.assertFalse(review.photo)
        self.assertFalse(RecipePhotoCleanup.objects.exists())

    def test_photo_rate_limit_precedes_image_normalization(self):
        with (
            patch("apps.recipe_book.reviews.reserve_review", side_effect=ReviewLimited(60)),
            patch("apps.recipe_book.reviews.normalize_review_photo") as normalize,
        ):
            with self.assertRaises(ReviewLimited):
                attach_review_photo(
                    self.user,
                    self.recipe.pk,
                    1,
                    jpeg_upload(),
                    permission_granted=True,
                )
        normalize.assert_not_called()

    def test_photo_resolution_over_16_megapixels_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Resolusi foto terlalu besar"):
            normalize_review_photo(jpeg_upload(width=4001, height=4000))

    def test_photo_audit_reports_missing_references_and_unqueued_orphans(self):
        from django.core.files.storage import default_storage

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            RecipeReview.objects.create(
                user=self.user,
                recipe=self.recipe,
                rating=5,
                photo="recipe-reviews/TEST-SUP/missing.jpg",
            )
            default_storage.save(
                "recipe-reviews/TEST-SUP/orphan.jpg", ContentFile(b"orphan")
            )
            output = StringIO()
            call_command("audit_recipe_review_photos", stdout=output)
            self.assertIn("Referenced=1", output.getvalue())
            self.assertIn("missing=1", output.getvalue())
            self.assertIn("orphaned=1", output.getvalue())
            with self.assertRaises(CommandError):
                call_command("audit_recipe_review_photos", fail_on_issues=True)

    def test_rating_comment_and_nested_json_validation(self):
        for value in (0, 6, True, "5", 2.5, None, {}):
            self.assertEqual(self.post_review(rating=value).status_code, 400)
        for value in ("x" * 501, {}, 123, True):
            self.assertEqual(self.post_review(comment=value).status_code, 400)
        self.assertEqual(
            self.client.post(
                reverse("modul4-review"),
                "[" * 1200 + "0" + "]" * 1200,
                content_type="application/json",
            ).status_code,
            400,
        )

    def test_constraint_prevents_duplicates_and_out_of_range_ratings(self):
        RecipeReview.objects.create(user=self.user, recipe=self.recipe, rating=5)
        for user, rating in ((self.user, 4), (self.other, 6)):
            with self.assertRaises(IntegrityError), transaction.atomic():
                RecipeReview.objects.create(user=user, recipe=self.recipe, rating=rating)

    @override_settings(SECRET_KEY="review-alias-test-key")
    def test_legacy_alias_is_stable_distinct_and_does_not_replace_regular_username(self):
        first = get_user_model().objects.create_user("first@example.com", "first@example.com")
        second = get_user_model().objects.create_user("second@example.com", "second@example.com")
        alias = public_username(first)
        self.assertEqual(alias, public_username(get_user_model().objects.get(pk=first.pk)))
        self.assertNotEqual(alias, public_username(second))
        self.assertEqual(public_username(self.user), self.user.username)

    def test_legacy_alias_is_keyed_not_an_unprotected_hash_of_sequential_id(self):
        legacy = get_user_model().objects.create_user("private@example.com")
        with override_settings(SECRET_KEY="first-alias-key"):
            first = public_username(legacy)
        with override_settings(SECRET_KEY="second-alias-key"):
            second = public_username(legacy)
        self.assertNotEqual(first, second)

    def test_hidden_review_stays_hidden_when_user_edits(self):
        self.cooked()
        self.post_review()
        RecipeReview.objects.update(is_hidden=True)
        self.assertEqual(self.post_review(version=1, is_hidden=False).status_code, 200)
        self.assertTrue(RecipeReview.objects.get().is_hidden)

    def test_rate_limit_shared_across_clients_and_resets_after_window(self):
        for _ in range(10):
            self.assertEqual(self.post_review().status_code, 403)
        fresh = Client()
        fresh.force_login(self.user)
        response = fresh.post(
            reverse("modul4-review"),
            json.dumps({"recipe_code": self.recipe.pk, "rating": 5}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response["Retry-After"]), 0)
        self.assertContains(response, "10 upaya", status_code=429)
        ReviewQuota.objects.update(window_started_at=timezone.now() - timedelta(minutes=11))
        self.assertEqual(self.post_review().status_code, 403)

    def test_guest_method_and_csrf_protection(self):
        self.assertEqual(
            Client()
            .post(reverse("modul4-review"), "{}", content_type="application/json")
            .status_code,
            403,
        )
        self.assertEqual(self.client.get(reverse("modul4-review")).status_code, 405)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.user)
        self.assertEqual(
            csrf.post(reverse("modul4-review"), "{}", content_type="application/json").status_code,
            403,
        )

    def test_account_delete_cascades_reviews_and_plan_delete_preserves_eligibility(self):
        self.batch()
        slot = self.slot()
        self.payload.update(planned_meal=slot.pk, version=1)
        cook(self.user, self.payload)
        slot.plan.delete()
        self.assertEqual(self.post_review().status_code, 200)
        RecipeReview.objects.create(user=self.other, recipe=self.recipe, rating=4)
        self.user.delete()
        self.assertEqual(
            list(RecipeReview.objects.values_list("user_id", flat=True)), [self.other.pk]
        )
