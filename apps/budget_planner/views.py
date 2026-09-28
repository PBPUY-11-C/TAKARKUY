from datetime import timedelta

from django.shortcuts import render
from django.utils import timezone

from .forms import PlannerForm
from .planner import MEALS, build_plan


def planner_page(request):
    initial = {"budget": 150000, "days": 3, "servings": 2, "meal_types": MEALS, "target": "seimbang"}
    form = PlannerForm(request.POST if request.method == "POST" else None, initial=initial)
    result = None
    error = None
    if request.method == "POST" and form.is_valid():
        try:
            today = timezone.localdate()
            history = request.session.get("planner_meal_history", {})
            cutoff = today - timedelta(days=7)
            history = {
                date_text: meals for date_text, meals in history.items()
                if cutoff.isoformat() <= date_text <= (today + timedelta(days=7)).isoformat()
            }
            recent_codes = {code for meals in history.values() for code in meals.values()}
            prior_slot_recipes = {
                meal: [history.get((today + timedelta(days=offset)).isoformat(), {}).get(meal)
                       for offset in range(form.cleaned_data["days"])]
                for meal in MEALS
            }
            result = build_plan(**form.cleaned_data, recent_recipe_codes=recent_codes,
                                prior_slot_recipes=prior_slot_recipes)
            if result["within_budget"]:
                for day_plan in result["schedule"]:
                    planned_date = (today + timedelta(days=day_plan["number"] - 1)).isoformat()
                    history[planned_date] = {
                        meal["type"]: meal["recipe_code"] for meal in day_plan["meals"]
                    }
                request.session["planner_meal_history"] = history
        except ValueError as exc:
            error = str(exc)
    return render(request, "budget_planner/planner.html", {"form": form, "result": result, "error": error})
