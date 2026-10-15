from django.db import migrations


def forward(apps, schema_editor):
    """Drop ml/liter pack weights entered when that field was ignored for liquids.

    Those rows never got a conversion (grams_per_unit is empty), and the old label
    meant "per pack", not "per 1 unit". Weights in use (grams_per_unit set) stay.
    """
    apps.get_model("pantry", "PantryItem").objects.filter(
        unit__in=["ml", "liter"], pack_weight_g__isnull=False, grams_per_unit__isnull=True
    ).update(pack_weight_g=None)


class Migration(migrations.Migration):
    dependencies = [("pantry", "0014_shelflifeestimate")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
