import json
from datetime import date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.shortcuts import render
from django.utils import timezone

from .forms import PlannerForm
from .planner import MEALS, build_plan
from .trial import browser_trial, protect_trial_response, record_success, trial_state


def _encode_result(value):
    if isinstance(value, Decimal):
        return {"_decimal": str(value)}
    if isinstance(value, date):
        return {"_date": value.isoformat()}
    raise TypeError(f"Unsupported planner result type: {type(value).__name__}")


def _decode_result(value):
    if set(value) == {"_decimal"}:
        return Decimal(value["_decimal"])
    if set(value) == {"_date"}:
        return date.fromisoformat(value["_date"])
    return value


def _previous_guest_plan(request):
    saved = request.session.get("guest_last_plan")
    if not saved:
        return None, None
    form = PlannerForm(saved["inputs"])
    if not form.is_valid():
        return None, None
    result = json.loads(saved["result"], object_hook=_decode_result)
    return form, result


def planner_page(request):
    initial = {
        "budget": 150000,
        "days": 3,
        "servings": 2,
        "meal_types": MEALS,
        "targets": ["seimbang"],
    }
    form = PlannerForm(request.POST if request.method == "POST" else None, initial=initial)
    result = None
    error = None
    trial = browser_trial(request) if not request.user.is_authenticated else None
    blocked = bool(trial is not None and trial_state(trial)["remaining"] == 0)
    status = 200
    if request.method == "POST" and blocked:
        status = 429
        previous_form, result = _previous_guest_plan(request)
        if previous_form:
            form = previous_form
    elif request.method == "POST" and form.is_valid():
        try:
            today = timezone.localdate()
            history = request.session.get("planner_meal_history", {})
            cutoff = today - timedelta(days=7)
            history = {
                date_text: meals
                for date_text, meals in history.items()
                if cutoff.isoformat() <= date_text <= (today + timedelta(days=7)).isoformat()
            }
            recent_codes = {code for meals in history.values() for code in meals.values()}
            prior_slot_recipes = {
                meal: [
                    history.get((today + timedelta(days=offset)).isoformat(), {}).get(meal)
                    for offset in range(form.cleaned_data["days"])
                ]
                for meal in MEALS
            }
            result = build_plan(
                **form.cleaned_data,
                recent_recipe_codes=recent_codes,
                prior_slot_recipes=prior_slot_recipes,
            )
            if result["within_budget"]:
                if trial is not None and not record_success(trial):
                    # Another request may have used the final slot during calculation.
                    blocked, status = True, 429
                    previous_form, result = _previous_guest_plan(request)
                    if previous_form:
                        form = previous_form
                else:
                    for day_plan in result["schedule"]:
                        planned_date = (today + timedelta(days=day_plan["number"] - 1)).isoformat()
                        history[planned_date] = {
                            meal["type"]: meal["recipe_code"] for meal in day_plan["meals"]
                        }
                    request.session["planner_meal_history"] = history
                    if trial is not None:
                        request.session["guest_last_plan"] = {
                            "inputs": {
                                key: request.POST.getlist(key)
                                if key in {"meal_types", "targets"}
                                else request.POST.get(key, "")
                                for key in form.fields
                            },
                            "result": json.dumps(result, default=_encode_result),
                        }
        except ValueError as exc:
            error = str(exc)
    if trial is not None and request.method == "GET":
        previous_form, result = _previous_guest_plan(request)
        if previous_form:
            form = previous_form
    state = trial_state(trial) if trial is not None else None
    if state and state["reset_at"]:
        state["reset_label"] = (
            state["reset_at"].astimezone(ZoneInfo("Asia/Jakarta")).strftime("%d %b %Y, %H:%M")
        )
    response = render(
        request,
        "budget_planner/planner.html",
        {
            "form": form,
            "result": result,
            "error": error,
            "trial": state,
            "trial_blocked": status == 429,
        },
        status=status,
    )
    return protect_trial_response(response, trial) if trial is not None else response
