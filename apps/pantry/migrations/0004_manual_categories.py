from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pantry", "0003_pack_unit"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pantryitem",
            name="category",
            field=models.CharField(
                blank=True,
                choices=[
                    ("sayur_buah", "Sayur & Buah"),
                    ("daging_seafood", "Daging & Seafood"),
                    ("tahu_tempe_kacang", "Tahu, Tempe & Kacang"),
                    ("beras_karbohidrat", "Beras & Karbohidrat"),
                    ("bumbu_minyak", "Bumbu & Minyak"),
                    ("lainnya", "Lainnya"),
                    ("sayuran", "Sayuran (kategori lama)"),
                    ("buah", "Buah (kategori lama)"),
                    ("protein_hewani", "Protein Hewani (kategori lama)"),
                    ("protein_nabati", "Protein Nabati (kategori lama)"),
                    ("bahan_pokok", "Bahan Pokok (kategori lama)"),
                ],
                default="",
                max_length=30,
            ),
        ),
    ]
