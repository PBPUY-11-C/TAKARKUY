"""Publication guard, including snapshots made before a catalog refresh.

Mendeley's dataset license is recorded, but the origin/permission for the
embedded cooking prose has not been independently reviewed. Do not publish it
until a per-recipe review workflow exists. This is not a nutritional approval.
"""

MENDELEY_URL = "https://data.mendeley.com/datasets/8b4ztns76h/3"


def protect_recipe_instructions(meal):
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
