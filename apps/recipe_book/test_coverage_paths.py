import json
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib import admin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Recipe
from apps.pantry.services import StockError

from . import tests as cooking_tests
from .admin import RecipeDataReportAdmin, RecipeReviewAdmin
from .management.commands.audit_recipe_review_photos import _stored_review_photos
from .models import RecipeDataReport, RecipePhotoCleanup, RecipeReview
from .photo_storage import (
    attempt_recipe_photo_cleanup,
    discard_uncommitted_recipe_photo,
    enqueue_recipe_photo_cleanup,
)
from .services import _apply_external_ingredients, recipe_requirements


class PhotoCleanupCoverageTests(TestCase):
    def test_cleanup_missing_and_storage_failure_paths(self):
        self.assertTrue(attempt_recipe_photo_cleanup(999999))
        job = RecipePhotoCleanup.objects.create(storage_name="recipe-reviews/fail.jpg")
        with patch("apps.recipe_book.photo_storage.default_storage.delete", side_effect=OSError("offline")):
            self.assertFalse(attempt_recipe_photo_cleanup(job.pk))
        job.refresh_from_db()
        self.assertEqual(job.attempts, 1)
        self.assertIn("offline", job.last_error)

    def test_enqueue_empty_deduplicates_and_runs_after_commit(self):
        self.assertIsNone(enqueue_recipe_photo_cleanup(""))
        with patch("apps.recipe_book.photo_storage.default_storage.delete") as delete:
            with self.captureOnCommitCallbacks(execute=True):
                first = enqueue_recipe_photo_cleanup("recipe-reviews/same.jpg")
                second = enqueue_recipe_photo_cleanup("recipe-reviews/same.jpg")
            self.assertEqual(first, second)
            delete.assert_called_once_with("recipe-reviews/same.jpg")
        self.assertFalse(RecipePhotoCleanup.objects.exists())

    def test_uncommitted_photo_is_removed_or_queued_without_masking_error(self):
        with patch("apps.recipe_book.photo_storage.default_storage.delete") as delete:
            discard_uncommitted_recipe_photo("recipe-reviews/new.jpg")
            delete.assert_called_once()
        with patch("apps.recipe_book.photo_storage.default_storage.delete", side_effect=OSError("offline")):
            discard_uncommitted_recipe_photo("recipe-reviews/queued.jpg")
        self.assertTrue(RecipePhotoCleanup.objects.filter(storage_name="recipe-reviews/queued.jpg").exists())
        with (
            patch("apps.recipe_book.photo_storage.default_storage.delete", side_effect=OSError("offline")),
            patch("apps.recipe_book.photo_storage.enqueue_recipe_photo_cleanup", side_effect=RuntimeError("db offline")),
        ):
            discard_uncommitted_recipe_photo("recipe-reviews/unqueueable.jpg")


class PhotoAuditCoverageTests(TestCase):
    setUp = cooking_tests.CookingTests.setUp

    def test_storage_listing_handles_missing_nested_and_unsupported(self):
        class Storage:
            def __init__(self, mode):
                self.mode = mode

            def listdir(self, path):
                if self.mode == "missing":
                    raise FileNotFoundError
                if self.mode == "error":
                    raise OSError("unavailable")
                if path == "recipe-reviews":
                    return ["nested"], ["root.jpg"]
                return [], ["child.jpg"]

        self.assertEqual(_stored_review_photos(Storage("missing")), set())
        self.assertEqual(
            _stored_review_photos(Storage("nested")),
            {"recipe-reviews/root.jpg", "recipe-reviews/nested/child.jpg"},
        )
        self.assertIsNone(_stored_review_photos(Storage("error")))

    def test_audit_reports_missing_storage_errors_and_fail_on_issues(self):
        RecipeReview.objects.create(user=self.user, recipe=self.recipe, rating=5, photo="missing.jpg")
        with (
            patch("apps.recipe_book.management.commands.audit_recipe_review_photos.default_storage.exists", return_value=False),
            patch("apps.recipe_book.management.commands.audit_recipe_review_photos.default_storage.listdir", return_value=([], [])),
        ):
            output = StringIO()
            with self.assertRaises(CommandError):
                call_command("audit_recipe_review_photos", fail_on_issues=True, stdout=output)
            self.assertIn("missing=1", output.getvalue())
        with (
            patch("apps.recipe_book.management.commands.audit_recipe_review_photos.default_storage.exists", side_effect=OSError("offline")),
            patch("apps.recipe_book.management.commands.audit_recipe_review_photos.default_storage.listdir", side_effect=NotImplementedError),
        ):
            output = StringIO()
            call_command("audit_recipe_review_photos", stdout=output)
            self.assertIn("storage_check_errors=1", output.getvalue())
            self.assertIn("orphaned=unsupported", output.getvalue())

    def test_audit_rejects_negative_stale_window_and_cleanup_command_reports_backlog(self):
        with self.assertRaises(CommandError):
            call_command("audit_recipe_review_photos", stale_minutes=-1)
        RecipePhotoCleanup.objects.create(storage_name="recipe-reviews/stuck.jpg")
        with patch("apps.recipe_book.photo_storage.default_storage.delete", side_effect=OSError("offline")):
            output = StringIO()
            call_command("cleanup_recipe_review_photos", stdout=output)
        self.assertIn("0 photo files; 1 cleanup job(s) remain", output.getvalue())


class RecipeBookBranchCoverageTests(TestCase):
    setUp = cooking_tests.CookingTests.setUp
    batch = cooking_tests.CookingTests.batch
    slot = cooking_tests.CookingTests.slot
    post = cooking_tests.CookingTests.post

    def test_external_ingredient_validation_and_partial_fulfillment(self):
        needs = {self.ingredient.pk: Decimal("60")}
        ingredients = [{"ingredient_code": self.ingredient.pk, "name": "Bayam", "tracked": True}]
        allocation = {"missing": {self.ingredient.pk: Decimal("60")}}
        for invalid in (None, ["bad"], [{"ingredient_code": "OTHER", "grams": 1}],
                        [{"ingredient_code": self.ingredient.pk, "grams": "bad"}],
                        [{"ingredient_code": self.ingredient.pk, "grams": 0}],
                        [{"ingredient_code": self.ingredient.pk, "grams": 61}],
                        [{"ingredient_code": self.ingredient.pk, "grams": 10},
                         {"ingredient_code": self.ingredient.pk, "grams": 10}],
                        [object()]):
            with self.subTest(invalid=invalid), self.assertRaises(StockError):
                _apply_external_ingredients(
                    {"external_ingredients": invalid}, needs, ingredients, {"missing": dict(allocation["missing"])}
                )
        partial = {"missing": {self.ingredient.pk: Decimal("60")}}
        result = _apply_external_ingredients(
            {"external_ingredients": [{"ingredient_code": self.ingredient.pk, "grams": "20"}]},
            needs, ingredients, partial,
        )
        self.assertEqual(result[0]["name"], "Bayam")
        self.assertEqual(partial["missing"][self.ingredient.pk], Decimal("40"))
        full = {"missing": {self.ingredient.pk: Decimal("60")}}
        _apply_external_ingredients(
            {"external_ingredients": [{"ingredient_code": self.ingredient.pk, "grams": "60"}]},
            needs, ingredients, full,
        )
        self.assertEqual(full["missing"], {})

    def test_requirements_validation_and_unverified_nutrition(self):
        with self.assertRaises(StockError):
            recipe_requirements(self.recipe, 0)
        without_base = Recipe.objects.create(recipe_code="NO-BASE", name="Tanpa porsi", base_servings=0,
                                             meal_type="makan_malam", is_plannable=True,
                                             instructions="", instruction_status="withheld")
        with self.assertRaises(StockError):
            recipe_requirements(without_base, 1)
        self.ingredient.calories_per_100g = None
        self.ingredient.save(update_fields=["calories_per_100g"])
        _, rows, nutrition = recipe_requirements(self.recipe, 2)
        self.assertIsNone(nutrition["calories"])
        self.assertTrue(rows[0]["tracked"])

    def test_report_api_validation_success_and_rate_limit(self):
        url = reverse("modul4-report-data")
        valid = {"recipe_code": self.recipe.pk, "category": "ingredients", "details": "Takaran perlu diperiksa"}
        for payload in (
            {**valid, "recipe_code": 4},
            {**valid, "category": "unknown"},
            {**valid, "details": "no"},
        ):
            self.assertEqual(self.client.post(url, json.dumps(payload), content_type="application/json").status_code, 400)
        response = self.client.post(url, json.dumps(valid), content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(RecipeDataReport.objects.count(), 1)
        for index in range(4):
            RecipeDataReport.objects.create(recipe=self.recipe, reporter=self.user, category="ingredients", details=f"laporan {index}")
        response = self.client.post(url, json.dumps(valid), content_type="application/json")
        self.assertEqual(response.status_code, 429)

    def test_upload_and_photo_endpoint_error_paths(self):
        from apps.recipe_book.views import recipe_review_photo

        factory = RequestFactory()
        request = factory.post("/modul4/review/photo/", data={"version": "1"})
        request.user = self.user
        request.META["CONTENT_LENGTH"] = "invalid"
        self.assertEqual(recipe_review_photo(request).status_code, 400)
        request = factory.post(
            "/modul4/review/photo/",
            data={"photo": SimpleUploadedFile("large.jpg", b"x"), "version": "1"},
        )
        request.user = self.user
        request.META["CONTENT_LENGTH"] = str(7 * 1024 * 1024 + 1)
        self.assertEqual(recipe_review_photo(request).status_code, 413)
        request = factory.post("/modul4/review/photo/")
        request.user = self.user
        self.assertEqual(recipe_review_photo(request).status_code, 400)
        request = factory.post("/modul4/review/photo/", data={"photo": SimpleUploadedFile("x.jpg", b"x"), "version": "bad"})
        request.user = self.user
        self.assertEqual(recipe_review_photo(request).status_code, 400)

    def test_slot_status_validation_and_owner_guard(self):
        url = reverse("modul4-slot-status")
        for payload in ({"planned_meal": 0, "status": "skipped", "version": 1},
                        {"planned_meal": 1, "status": "skipped"},
                        {"planned_meal": 999999, "status": "skipped", "version": 1}):
            response = self.client.post(url, json.dumps(payload), content_type="application/json")
            self.assertIn(response.status_code, (400, 404))
        slot = self.slot()
        payload = {"planned_meal": slot.pk, "status": "skipped", "version": slot.plan.version}
        self.assertEqual(self.client.post(url, json.dumps(payload), content_type="application/json").status_code, 200)


class RecipeAdminCoverageTests(TestCase):
    setUp = cooking_tests.CookingTests.setUp

    def test_admin_report_assignment_filter_and_add_permissions(self):
        report_admin = RecipeDataReportAdmin(RecipeDataReport, admin.site)
        request = RequestFactory().get("/admin/")
        field = RecipeDataReport._meta.get_field("assigned_to")
        formfield = report_admin.formfield_for_foreignkey(field, request)
        self.assertEqual(formfield.queryset.count(), 0)
        self.assertFalse(report_admin.has_add_permission(request))
        review_admin = RecipeReviewAdmin(RecipeReview, admin.site)
        self.assertFalse(review_admin.has_add_permission(request))

    def test_review_admin_actions_and_display_helpers(self):
        staff = type(self.user).objects.create_user("staff", is_staff=True)
        request = RequestFactory().post("/admin/")
        request.user = staff
        review = RecipeReview.objects.create(user=self.user, recipe=self.recipe, rating=5,
                                             photo="photo.jpg", photo_permission_granted=True,
                                             photo_consent_at=timezone.now(), photo_is_hidden=True)
        review_admin = RecipeReviewAdmin(RecipeReview, admin.site)
        self.assertIn("Menunggu", review_admin.photo_moderation(review))
        self.assertEqual(review_admin.photo_consent(review), "Tercatat")
        review_admin.approve_consented_photos(request, RecipeReview.objects.filter(pk=review.pk))
        review.refresh_from_db()
        self.assertFalse(review.photo_is_hidden)
        first_version = review.version
        review_admin.hide_selected_photos(request, RecipeReview.objects.filter(pk=review.pk))
        review.refresh_from_db()
        self.assertTrue(review.photo_is_hidden)
        self.assertGreater(review.version, first_version)
        review.photo = ""
        review.photo_permission_granted = False
        review.photo_consent_at = None
        self.assertEqual(review_admin.photo_moderation(review), "—")
        self.assertEqual(review_admin.photo_consent(review), "Tidak ada")
