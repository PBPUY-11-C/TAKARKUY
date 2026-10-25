from django.db import migrations, models

import apps.accounts.models


def keep_cooking_oil_stock_managed(apps, schema_editor):
    profile = apps.get_model("accounts", "UserProfile")
    profile.objects.all().update(tracked_staples=["cooking_oil"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_case_insensitive_identity")]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="tracked_staples",
            field=models.JSONField(default=list),
        ),
        migrations.RunPython(keep_cooking_oil_stock_managed, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="userprofile",
            name="tracked_staples",
            field=models.JSONField(default=apps.accounts.models.default_tracked_staples),
        ),
    ]
