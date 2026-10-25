from decimal import Decimal

from django.db import migrations


def backfill(apps, schema_editor):
    Batch = apps.get_model("pantry", "PantryItem")
    Movement = apps.get_model("pantry", "PantryMovement")
    Conversion = apps.get_model("catalog", "UnitConversion")
    alias = schema_editor.connection.alias
    conversions = {}
    for row in Conversion.objects.using(alias).order_by("conversion_code"):
        weight = Decimal(str(row.gram_equivalent or 0))
        if row.conversion_status in {"standard", "size_specific", "manual_curated", "reviewed"} and weight.is_finite() and 0 < weight < 1000000:
            conversions.setdefault((row.ingredient_id, row.unit), (weight, row.note or row.source))
    for item in Batch.objects.using(alias).iterator():
        item.base_unit = "g" if item.unit in {"g", "kg"} else "ml" if item.unit in {"ml", "liter"} else "pcs"
        if item.unit in {"g", "kg"}:
            item.grams_per_unit = Decimal(1 if item.unit == "g" else 1000)
            item.conversion_note = "Satuan berat."
        else:
            item.grams_per_unit, item.conversion_note = conversions.get((item.ingredient_id, item.unit), (None, "Konversi berat belum diketahui."))
        item.expiry_source = "unknown"
        item.conversion_note = item.conversion_note[:255]
        item.save(using=alias, update_fields=["base_unit", "grams_per_unit", "conversion_note", "expiry_source"])
        entry = Movement.objects.using(alias).create(batch_id=item.pk, kind="in", quantity_before=0,
            quantity_after=item.quantity, snapshot={"migration": True, "after": {
                "name": item.name, "unit": item.unit, "quantity": str(item.quantity),
                "location": item.location, "expiry_source": "unknown",
                "estimated_expires_on": str(item.estimated_expires_on or ""),
                "ingredient_id": item.ingredient_id, "grams_per_unit": str(item.grams_per_unit or ""),
            }})
        Movement.objects.using(alias).filter(pk=entry.pk).update(created_at=item.added_at)


def reverse_backfill(apps, schema_editor):
    apps.get_model("pantry", "PantryMovement").objects.using(schema_editor.connection.alias).filter(snapshot__migration=True).delete()


class Migration(migrations.Migration):
    dependencies = [("pantry", "0009_nameresolution_pantryllmusage_pantrymovement_and_more")]
    operations = [migrations.RunPython(backfill, reverse_backfill)]
