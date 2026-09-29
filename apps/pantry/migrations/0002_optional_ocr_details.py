from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pantry", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pantryitem",
            name="category",
            field=models.CharField(
                blank=True,
                choices=[
                    ("sayuran", "Sayuran"), ("buah", "Buah"),
                    ("protein_hewani", "Protein Hewani"),
                    ("protein_nabati", "Protein Nabati"),
                    ("bahan_pokok", "Bahan Pokok"), ("lainnya", "Lainnya"),
                ],
                default="",
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="pantryitem",
            name="location",
            field=models.CharField(
                blank=True,
                choices=[
                    ("chiller", "Kulkas Bawah (Chiller)"),
                    ("freezer", "Freezer"), ("suhu_ruang", "Suhu Ruang"),
                    ("lemari_kering", "Lemari Kering"),
                ],
                default="",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="pantryitem",
            name="shelf_life_days",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="pantryitem",
            name="estimated_expires_on",
            field=models.DateField(blank=True, null=True),
        ),
    ]
