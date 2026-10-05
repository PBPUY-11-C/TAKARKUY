"""Exercise historical schema while retaining owners, IDs and old dates."""

from datetime import date
from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class BatchMigrationTests(TransactionTestCase):
    old = ("pantry", "0008_pantryitem_user_pantrynamecorrection_user_and_more")
    new = ("pantry", "0012_pantrynamecorrection_confirmed_by_user_and_more")

    def test_existing_stock_becomes_batch_with_initial_movement(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.old])
        try:
            apps = executor.loader.project_state([self.old]).apps
            User = apps.get_model("auth", "User")
            Batch = apps.get_model("pantry", "PantryItem")
            owner = User.objects.create(username="legacy-owner")
            Ingredient = apps.get_model("catalog", "Ingredient")
            ingredient = Ingredient.objects.create(
                ingredient_code="ING-LEGACY", name="Bayam", category="sayur", base_unit="g"
            )
            correction = apps.get_model("pantry", "PantryNameCorrection").objects.create(
                user_id=owner.pk,
                session_id="legacy",
                raw_name="BYM",
                normalized_name="bym",
                ingredient_id=ingredient.pk,
            )
            item = Batch.objects.create(
                user_id=owner.pk,
                session_id="legacy",
                name="Lama",
                unit="kg",
                quantity="2.500",
                source="manual",
                starting_on=date(2026, 9, 1),
                estimated_expires_on=date(2026, 10, 20),
            )
            anonymous = Batch.objects.create(
                session_id="anonymous", name="Tanpa Pemilik", unit="pack", quantity=0, source="ocr"
            )
            executor = MigrationExecutor(connection)
            executor.migrate([self.new])
            apps = executor.loader.project_state([self.new]).apps
            Batch = apps.get_model("pantry", "PantryItem")
            Movement = apps.get_model("pantry", "PantryMovement")
            migrated = Batch.objects.get(pk=item.pk)
            self.assertEqual(migrated.user_id, owner.pk)
            self.assertEqual(migrated.quantity, Decimal("2.500"))
            self.assertEqual(migrated.estimated_expires_on, date(2026, 10, 20))
            self.assertEqual(migrated.starting_on, date(2026, 9, 1))
            self.assertEqual(migrated.expiry_source, "legacy")
            self.assertEqual(migrated.grams_per_unit, 1000)
            self.assertEqual(migrated.base_unit, "g")
            self.assertIsNone(Batch.objects.get(pk=anonymous.pk).user_id)
            self.assertEqual(Batch.objects.get(pk=anonymous.pk).expiry_source, "unknown")
            self.assertEqual(Movement.objects.count(), 2)
            entry = Movement.objects.get(batch_id=item.pk)
            self.assertEqual(entry.quantity_before, 0)
            self.assertEqual(entry.quantity_after, migrated.quantity)
            self.assertEqual(entry.created_at, item.added_at)
            Correction = apps.get_model("pantry", "PantryNameCorrection")
            self.assertFalse(Correction.objects.get(pk=correction.pk).confirmed_by_user)
            executor = MigrationExecutor(connection)
            executor.migrate([("pantry", "0011_alter_pantrymovement_operation")])
            old_apps = executor.loader.project_state(
                [("pantry", "0011_alter_pantrymovement_operation")]
            ).apps
            rolled_back = old_apps.get_model("pantry", "PantryItem").objects.get(pk=item.pk)
            self.assertEqual(rolled_back.expiry_source, "unknown")
            self.assertEqual(rolled_back.estimated_expires_on, date(2026, 10, 20))
            Batch = old_apps.get_model("pantry", "PantryItem")
            fresh = Batch.objects.create(
                user_id=owner.pk,
                session_id="fresh",
                name="New unknown",
                quantity=1,
                unit="g",
                source="manual",
                expiry_source="unknown",
                estimated_expires_on=date(2026, 10, 20),
            )
            manual = Batch.objects.create(
                user_id=owner.pk,
                session_id="fresh",
                name="New manual",
                quantity=1,
                unit="g",
                source="manual",
                expiry_source="manual",
                estimated_expires_on=date(2026, 10, 20),
            )
            executor = MigrationExecutor(connection)
            executor.migrate([self.new])
            Batch = executor.loader.project_state([self.new]).apps.get_model("pantry", "PantryItem")
            self.assertEqual(Batch.objects.get(pk=fresh.pk).expiry_source, "unknown")
            self.assertEqual(Batch.objects.get(pk=manual.pk).expiry_source, "manual")
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
