from django.db import migrations


def initialize(apps, schema_editor):
    Recipe = apps.get_model("catalog", "Recipe")
    Group = apps.get_model("catalog", "RecipeAllergen")
    keys = {"telur", "susu", "kacang_tanah", "kedelai", "gluten", "ikan",
            "krustasea", "moluska", "wijen", "kacang_pohon", "sulfit"}
    rows, groups = [], []
    for recipe in Recipe.objects.prefetch_related("recipeingredient_set__ingredient", "recipetag_set"):
        links = list(recipe.recipeingredient_set.all())
        reviewed = bool(links) and not any(
            tag.tag == "bumbu_minor_tidak_dihitung" for tag in recipe.recipetag_set.all()
        )
        values = set()
        for link in links:
            allergens = link.ingredient.allergens
            valid = isinstance(allergens, list) and all(isinstance(v, str) and v in keys for v in allergens)
            reviewed = reviewed and link.ingredient.allergen_status == "reviewed" and valid
            if valid:
                values.update(allergens)
        recipe.allergen_reviewed = bool(reviewed)
        if recipe.instructions.strip() and not recipe.pk.startswith("RCP-MDL-"):
            recipe.instruction_status = "source_ok"
            recipe.instruction_review_note = "Panduan yang sebelumnya diterbitkan menurut kebijakan katalog; bukan review hak pakai baru."
        groups.extend(Group(recipe_id=recipe.pk, group=value) for value in sorted(values))
        rows.append(recipe)
    Recipe.objects.bulk_update(rows, ["allergen_reviewed", "instruction_status", "instruction_review_note"])
    Group.objects.bulk_create(groups, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0004_recipe_allergen_reviewed_and_more")]
    operations = [migrations.RunPython(initialize, migrations.RunPython.noop)]
