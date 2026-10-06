import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import tests as cooking_tests
from .models import CookingHistory, RecipeReview, ReviewQuota
from .reviews import public_username, review_context
from .services import cook


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

    def test_public_stats_hide_moderated_reviews_and_never_publish_email(self):
        legacy = get_user_model().objects.create_user("private@example.com", "private@example.com")
        RecipeReview.objects.create(
            user=legacy, recipe=self.recipe, rating=5, comment='<img src=x onerror="alert(1)">'
        )
        RecipeReview.objects.create(user=self.other, recipe=self.recipe, rating=3)
        RecipeReview.objects.create(user=self.user, recipe=self.recipe, rating=1, is_hidden=True)
        data = review_context(self.user, self.recipe)
        self.assertEqual(data["review_stats"], {"average": 4, "count": 2})
        self.assertRegex(public_username(legacy), r"^Penakar #[0-9a-f]{12}$")
        self.assertNotEqual(public_username(legacy), f"Penakar #{legacy.pk}")
        response = self.client.get(reverse("modul4"), {"recipe": self.recipe.pk})
        self.assertNotContains(response, "private@example.com")
        self.assertContains(response, public_username(legacy))
        self.assertContains(response, "&lt;img")
        self.assertNotContains(response, '<img src=x onerror="alert(1)">')

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
