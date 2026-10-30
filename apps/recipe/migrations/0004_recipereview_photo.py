import apps.recipe.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("recipe_book", "0003_reviewquota_recipereview")]

    operations = [
        migrations.AddField(
            model_name="recipereview",
            name="photo",
            field=models.FileField(
                blank=True,
                upload_to=apps.recipe.models.recipe_review_photo_path,
            ),
        ),
        migrations.AddField(
            model_name="recipereview",
            name="photo_is_hidden",
            field=models.BooleanField(db_index=True, default=True),
        ),
    ]
