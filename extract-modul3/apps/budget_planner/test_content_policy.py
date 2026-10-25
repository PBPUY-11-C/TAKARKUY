from copy import deepcopy

from django.test import SimpleTestCase

from apps.catalog.content_policy import protect_plan_instructions

from .snapshots import freeze, thaw


class RecipePublicationTests(SimpleTestCase):
    def test_unreviewed_source_instructions_are_not_returned_even_from_old_snapshots(self):
        original = {
            "schedule": [
                {
                    "meals": [
                        {
                            "recipe_code": "RCP-MDL-0001",
                            "name": "Menu",
                            "instructions": "Teks sumber lama",
                        }
                    ]
                }
            ]
        }
        stored = freeze(original)
        displayed = thaw(stored)
        meal = displayed["schedule"][0]["meals"][0]
        self.assertEqual(meal["instructions"], "")
        self.assertTrue(meal["instructions_pending_review"])
        self.assertIn("CC BY 4.0", meal["recipe_attribution"])
        self.assertTrue(displayed["instructions_pending_review"])
        # Publication filtering is non-mutating for the persisted historical snapshot.
        self.assertEqual(stored, original)

    def test_original_team_instructions_are_preserved(self):
        original = {
            "schedule": [
                {
                    "meals": [
                        {
                            "recipe_code": "RCP-MVP-001",
                            "instructions": "Langkah buatan tim",
                        }
                    ]
                }
            ]
        }
        self.assertEqual(protect_plan_instructions(deepcopy(original)), original)

    def test_policy_is_idempotent(self):
        result = {"schedule": [{"meals": [{"recipe_code": "RCP-MDL-0001"}]}]}
        once = protect_plan_instructions(result)
        self.assertEqual(protect_plan_instructions(deepcopy(once)), once)
