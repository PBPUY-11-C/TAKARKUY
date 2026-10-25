from django.db import migrations, models

import apps.accounts.models


def move_tracked_staples(apps, schema_editor):
    alias = schema_editor.connection.alias
    Profile = apps.get_model("accounts", "UserProfile")
    Preference = apps.get_model("accounts", "FoodPreference")
    for profile in Profile.objects.using(alias).only("user_id", "tracked_staples").iterator():
        Preference.objects.using(alias).filter(user_id=profile.user_id).update(
            tracked_staples=profile.tracked_staples
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_foodpreference_and_more"),
        ("accounts", "0003_userprofile_tracked_staples"),
    ]

    operations = [
        migrations.AddField(
            model_name="foodpreference",
            name="tracked_staples",
            field=models.JSONField(default=apps.accounts.models.default_tracked_staples),
        ),
        migrations.RunPython(move_tracked_staples, migrations.RunPython.noop),
        migrations.RemoveField(model_name="userprofile", name="tracked_staples"),
    ]
