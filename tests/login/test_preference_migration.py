from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class PreferenceMigrationTests(TransactionTestCase):
    def rollback_preferences(self):
        MigrationExecutor(connection).migrate([("accounts", None)])

    def test_avatar_upgrade_keeps_existing_profile_and_food_preferences(self):
        before = [("accounts", "0004_tracked_staples_on_food_preference")]
        after = [("accounts", "0005_merge_avatar_and_tracked_staples")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        self.rollback_preferences()
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        try:
            apps = executor.loader.project_state(before).apps
            user = apps.get_model(settings.AUTH_USER_MODEL).objects.create(username="old-avatar-owner")
            apps.get_model("accounts", "UserProfile").objects.create(user_id=user.pk, version=8)
            apps.get_model("accounts", "FoodPreference").objects.create(user_id=user.pk, servings=4)
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            apps = executor.loader.project_state(after).apps
            profile = apps.get_model("accounts", "UserProfile").objects.get(user_id=user.pk)
            self.assertEqual(profile.avatar, "initials")
            self.assertEqual(profile.version, 8)
            self.assertEqual(
                apps.get_model("accounts", "FoodPreference").objects.get(user_id=user.pk).servings, 4
            )
        finally:
            MigrationExecutor(connection).migrate(latest)

    def test_existing_preferences_and_avoided_ingredients_survive_split_and_rollback(self):
        before = [("accounts", "0002_case_insensitive_identity")]
        after = [("accounts", "0003_foodpreference_and_more")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        self.rollback_preferences()
        MigrationExecutor(connection).migrate(before)
        try:
            old_apps = executor.loader.project_state(before).apps
            User = old_apps.get_model(settings.AUTH_USER_MODEL)
            user = User.objects.create(username="migration-owner")
            Ingredient = old_apps.get_model("catalog", "Ingredient")
            ingredient = Ingredient.objects.create(
                ingredient_code="MIGRATION-AVOID", name="Bahan dihindari",
                category="sayur", base_unit="g",
            )
            Profile = old_apps.get_model("accounts", "UserProfile")
            profile = Profile.objects.create(
                user_id=user.pk, targets=["tinggi_protein"], meal_types=["sarapan"],
                servings=4, allergens=["telur"], version=7,
            )
            profile.avoided_ingredients.add(ingredient)
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            apps = executor.loader.project_state(after).apps
            preference = apps.get_model("accounts", "FoodPreference").objects.get(user_id=user.pk)
            self.assertEqual(preference.targets, ["tinggi_protein"])
            self.assertEqual(preference.meal_types, ["sarapan"])
            self.assertEqual(preference.servings, 4)
            self.assertEqual(preference.allergens, ["telur"])
            self.assertTrue(preference.halal_only)
            self.assertEqual(list(preference.avoided_ingredients.values_list("pk", flat=True)), [ingredient.pk])
            self.assertEqual(apps.get_model("accounts", "UserProfile").objects.get(user_id=user.pk).version, 7)
            MigrationExecutor(connection).migrate(before)
            apps = executor.loader.project_state(before).apps
            restored = apps.get_model("accounts", "UserProfile").objects.get(user_id=user.pk)
            self.assertEqual(restored.targets, ["tinggi_protein"])
            self.assertEqual(restored.servings, 4)
            self.assertEqual(restored.allergens, ["telur"])
            self.assertEqual(list(restored.avoided_ingredients.values_list("pk", flat=True)), [ingredient.pk])
        finally:
            MigrationExecutor(connection).migrate(latest)
