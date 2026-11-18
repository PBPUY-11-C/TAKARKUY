"""Penjaga publikasi panduan resep, termasuk snapshot yang dibuat sebelum katalog diperbarui."""

MENDELEY_URL = "https://data.mendeley.com/datasets/8b4ztns76h/3"


def protect_recipe_instructions(meal):
    """Mengosongkan panduan yang ditahan atau resep Mendeley belum ditinjau (dict diubah langsung);
    resep Mendeley selalu diberi URL sumber dan atribusi CC BY 4.0."""
    code = meal.get("recipe_code", "")
    mendeley = isinstance(code, str) and code.startswith("RCP-MDL-")
    reviewed = (
        meal.get("instruction_status") in {"source_ok", "authored_reviewed"}
        and meal.get("instruction_review_note")
        and meal.get("instruction_reviewed_on")
    )
    if meal.get("instruction_status") == "withheld" or (mendeley and not reviewed):
        meal["instructions"] = ""
        meal["instructions_pending_review"] = True
    if mendeley:
        meal["recipe_source_url"] = MENDELEY_URL
        meal["recipe_attribution"] = "Purwanto, Wibawa & Devi · Mendeley Data v3 · CC BY 4.0"
    return meal


def protect_plan_instructions(result):
    """Menerapkan protect_recipe_instructions ke setiap menu di jadwal rencana; jika ada yang ditahan,
    rencana ditandai instructions_pending_review beserta URL sumber Mendeley."""
    held = False
    if isinstance(result, dict):
        for day in result.get("schedule", []):
            for meal in day.get("meals", []):
                protect_recipe_instructions(meal)
                held = held or meal.get("instructions_pending_review", False)
        if held:
            result["instructions_pending_review"] = True
            result["recipe_source_url"] = MENDELEY_URL
    return result
