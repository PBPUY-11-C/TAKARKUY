from django.db import migrations


def check_conflicts(apps, schema_editor):
    user = apps.get_model("auth", "User")
    q = schema_editor.connection.ops.quote_name
    table = q(user._meta.db_table)
    with schema_editor.connection.cursor() as cursor:
        for field in ("username", "email"):
            condition = f"WHERE {q(field)} <> ''" if field == "email" else ""
            cursor.execute(f"SELECT COUNT(*) FROM (SELECT lower({q(field)}) FROM {table} {condition} GROUP BY lower({q(field)}) HAVING COUNT(*) > 1) AS duplicates")
            if cursor.fetchone()[0]:
                raise RuntimeError(f"Migrasi dihentikan: ada {field} ganda tanpa membedakan kapital. Tinjau akun secara manual; tidak ada akun digabung atau dihapus.")
        cursor.execute(f"SELECT COUNT(*) FROM {table} a JOIN {table} b ON lower(a.username) = lower(b.email) WHERE a.id <> b.id AND b.email <> ''")
        if cursor.fetchone()[0]:
            raise RuntimeError("Migrasi dihentikan: username akun lama bertabrakan dengan email akun lain. Tinjau manual sebelum deploy.")


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial"), ("auth", "0012_alter_user_first_name_max_length")]
    operations = [
        migrations.RunPython(check_conflicts, migrations.RunPython.noop),
        migrations.RunSQL("CREATE UNIQUE INDEX accounts_user_username_ci ON auth_user (lower(username))", "DROP INDEX accounts_user_username_ci"),
        migrations.RunSQL("CREATE UNIQUE INDEX accounts_user_email_ci ON auth_user (lower(email)) WHERE email <> ''", "DROP INDEX accounts_user_email_ci"),
    ]
