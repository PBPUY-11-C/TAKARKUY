from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("pantry", "0004_manual_categories"),
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PantryNameCorrection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_id", models.CharField(db_index=True, max_length=32)),
                ("raw_name", models.CharField(max_length=255)),
                ("normalized_name", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("ingredient", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="catalog.ingredient")),
            ],
            options={
                "constraints": [models.UniqueConstraint(fields=("session_id", "normalized_name"), name="pantry_session_ocr_name_unique")],
            },
        ),
    ]
