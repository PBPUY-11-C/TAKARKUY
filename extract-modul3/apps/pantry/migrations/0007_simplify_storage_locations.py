from django.db import migrations, models


def normalize_legacy_locations(apps, schema_editor):
    PantryItem = apps.get_model("pantry", "PantryItem")
    PantryItem.objects.using(schema_editor.connection.alias).filter(location="lemari_kering").update(
        location="suhu_ruang"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("pantry", "0006_pantryitem_ingredient_pantryitem_starting_on_and_more"),
    ]

    operations = [
        migrations.RunPython(normalize_legacy_locations, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="pantryitem",
            name="location",
            field=models.CharField(
                blank=True,
                choices=[("chiller", "Kulkas"), ("freezer", "Freezer"), ("suhu_ruang", "Suhu Ruang")],
                default="suhu_ruang",
                max_length=20,
            ),
        ),
    ]
