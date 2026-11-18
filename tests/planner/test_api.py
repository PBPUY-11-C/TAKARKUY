import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.planner.models import BudgetPlan
from apps.planner.planner import build_plan
from apps.planner.services import clean_inputs, write_draft

INPUTS = {
    "budget": "1000000",
    "days": 1,
    "servings": 1,
    "meal_types": ["sarapan"],
    "targets": ["seimbang"],
    "exclude_ingredients": "",
}


class PlannerApiTests(TestCase):
    fixtures = ["catalog_seed"]

    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.user = users.create_user("planner", password="Demo1234!")
        cls.other = users.create_user("other", password="Demo1234!")
        cls.result = build_plan(**clean_inputs(INPUTS).cleaned_data, seed=1)
        assert cls.result["within_budget"]

    def setUp(self):
        self.client.force_login(self.user)

    def post(self, url, data):
        return self.client.post(url, data=json.dumps(data), content_type="application/json")

    def draft(self, user=None):
        return write_draft(user or self.user, dict(INPUTS), self.result)

    def saved(self, user=None):
        draft = self.draft(user)
        self.client.force_login(user or self.user)
        response = self.post(
            f"/api/planner/plans/{draft.pk}/save/", {"version": draft.version, "title": "Minggu ini"}
        )
        self.client.force_login(self.user)
        return BudgetPlan.objects.get(pk=response.json()["id"])

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get("/api/planner/plans/").status_code, 403)

    def test_list_only_returns_own_plans(self):
        mine = self.draft()
        self.draft(self.other)
        response = self.client.get("/api/planner/plans/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.json()], [str(mine.pk)])
        self.assertEqual(response.json()[0]["status"], "draft")

    def test_detail_returns_schedule_and_shopping_list(self):
        plan = self.draft()
        body = self.client.get(f"/api/planner/plans/{plan.pk}/").json()
        self.assertEqual(body["id"], str(plan.pk))
        self.assertEqual(body["version"], plan.version)
        self.assertEqual(len(body["result"]["schedule"]), 1)
        self.assertIn("shopping_groups", body["result"])

    def test_other_users_plan_is_not_found(self):
        plan = self.draft(self.other)
        self.assertEqual(self.client.get(f"/api/planner/plans/{plan.pk}/").status_code, 404)
        response = self.post(f"/api/planner/plans/{plan.pk}/delete/", {"version": plan.version})
        self.assertEqual(response.status_code, 404)
        self.assertTrue(BudgetPlan.objects.filter(pk=plan.pk).exists())

    def test_create_makes_a_draft(self):
        response = self.post("/api/planner/plans/", INPUTS)
        self.assertEqual(response.status_code, 201)
        plan = BudgetPlan.objects.get(user=self.user)
        self.assertEqual(response.json()["id"], str(plan.pk))
        self.assertEqual(plan.status, "draft")

    def test_create_rejects_invalid_inputs(self):
        response = self.post("/api/planner/plans/", {**INPUTS, "days": 99})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())
        self.assertFalse(BudgetPlan.objects.exists())

    def test_create_over_budget_returns_result_without_saving(self):
        response = self.post("/api/planner/plans/", {**INPUTS, "budget": "1"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["result"]["within_budget"])
        self.assertFalse(BudgetPlan.objects.exists())

    def test_create_needs_approval_to_replace_existing_draft(self):
        draft = self.draft()
        self.assertEqual(self.post("/api/planner/plans/", INPUTS).status_code, 409)
        response = self.post(
            "/api/planner/plans/",
            {
                **INPUTS,
                "replace_draft": True,
                "replace_draft_id": str(draft.pk),
                "replace_draft_version": draft.version,
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(BudgetPlan.objects.filter(user=self.user).count(), 1)

    def test_save_turns_draft_into_saved_plan_and_updates_title(self):
        plan = self.saved()
        self.assertEqual((plan.status, plan.title), ("saved", "Minggu ini"))
        response = self.post(
            f"/api/planner/plans/{plan.pk}/save/", {"version": plan.version, "title": "Ganti judul"}
        )
        self.assertEqual(response.status_code, 200)
        plan.refresh_from_db()
        self.assertEqual(plan.title, "Ganti judul")

    def test_save_validates_title(self):
        draft = self.draft()
        response = self.post(
            f"/api/planner/plans/{draft.pk}/save/", {"version": draft.version, "title": ""}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("title", response.json()["fields"])

    def test_stale_version_is_a_conflict(self):
        draft = self.draft()
        response = self.post(
            f"/api/planner/plans/{draft.pk}/save/", {"version": draft.version - 1, "title": "Lama"}
        )
        self.assertEqual(response.status_code, 409)

    def test_delete_removes_plan(self):
        plan = self.saved()
        response = self.post(f"/api/planner/plans/{plan.pk}/delete/", {"version": plan.version})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BudgetPlan.objects.filter(pk=plan.pk).exists())

    def test_form_posts_are_rejected(self):
        # API tidak memakai token CSRF, jadi hanya body JSON yang diterima: form lintas situs ditolak.
        draft = self.draft()
        response = self.client.post(
            f"/api/planner/plans/{draft.pk}/delete/", {"version": draft.version}
        )
        self.assertEqual(response.status_code, 415)
        self.assertTrue(BudgetPlan.objects.filter(pk=draft.pk).exists())

    def test_post_works_without_csrf_token(self):
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(
            "/api/planner/plans/", data=json.dumps(INPUTS), content_type="application/json"
        )
        self.assertEqual(response.status_code, 201)
