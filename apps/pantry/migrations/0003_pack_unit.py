from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pantry", "0002_optional_ocr_details"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pantryitem",
            name="unit",
            field=models.CharField(
                choices=[
                    ("g", "g"), ("kg", "kg"), ("ml", "ml"),
                    ("liter", "liter"), ("buah", "buah"),
                    ("ikat", "ikat"), ("butir", "butir"),
                    ("papan", "papan"), ("kotak", "kotak"),
                    ("bungkus", "bungkus"), ("botol", "botol"),
                    ("pak", "pak"), ("pack", "pack / bungkus"),
                ],
                max_length=20,
            ),
        ),
    ]
