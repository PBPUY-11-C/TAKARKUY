"""Eight bounded queries; dashboard reads source data without changing it."""

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.db.models import Case, CharField, Count, F, Max, Prefetch, Q, Value, When, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

from apps.budget_planner.models import BudgetPlan, PlannedMeal
from apps.budget_planner.services import draft_is_clean
from apps.pantry.models import PantryItem
from apps.recipe_book.models import CookingHistory

JAKARTA = ZoneInfo("Asia/Jakarta")
MEALS = {"sarapan": "Sarapan", "makan_siang": "Makan siang", "makan_malam": "Makan malam"}


def parse_money(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and 0 <= result <= Decimal("1e14") else None
    except InvalidOperation:
        return None


def dashboard_data(user):
    today = timezone.localdate(timezone=JAKARTA)
    plans = list(
        BudgetPlan.objects.filter(user=user, status="saved", starts_on__lte=today)
        .annotate(ends_on=Max("meals__scheduled_on"))
        .filter(ends_on__gte=today)
        .prefetch_related(
            Prefetch(
                "meals",
                queryset=PlannedMeal.objects.filter(scheduled_on=today)
                .select_related("recipe")
                .order_by("meal_type", "pk"),
                to_attr="today_meals",
            )
        )
        .order_by("-updated_at", "pk")
    )
    for plan in plans:
        inputs = plan.inputs if isinstance(plan.inputs, dict) else {}
        snapshot = plan.snapshot if isinstance(plan.snapshot, dict) else {}
        # The budget limits money still to spend after pantry stock (older plans: total).
        budget = parse_money(inputs.get("budget"))
        total = parse_money(snapshot.get("net_total", snapshot.get("total")))
        plan.remaining = budget - total if budget is not None and total is not None else None
        plan.over_budget = plan.remaining is not None and plan.remaining < 0
        if plan.over_budget:
            plan.remaining = -plan.remaining
        for meal in plan.today_meals:
            snapshot = meal.snapshot if isinstance(meal.snapshot, dict) else {}
            meal.display_name = (snapshot.get("name") or meal.recipe.name) + (
                " + Nasi" if snapshot.get("with_rice") else ""
            )
            meal.display_time = MEALS.get(meal.meal_type, meal.meal_type)
        plan.today_meals.sort(
            key=lambda meal: list(MEALS).index(meal.meal_type) if meal.meal_type in MEALS else 99
        )
    stock = PantryItem.objects.filter(user=user, archived_at__isnull=True, quantity__gt=0)
    unknown = Q(estimated_expires_on__isnull=True) | Q(expiry_source="unknown")
    expired = Q(estimated_expires_on__lt=today) & ~unknown
    soon = Q(estimated_expires_on__range=(today, today + timedelta(days=2))) & ~unknown
    stock_counts = stock.aggregate(
        total=Count("pk"),
        soon=Count("pk", filter=soon),
        unknown=Count("pk", filter=unknown),
        expired=Count("pk", filter=expired),
    )
    # At most three rows per category, not the entire pantry. Window queries work
    # on both supported SQLite and PostgreSQL; adding batches cannot cause N+1.
    priority = (
        stock.filter(unknown | expired | soon)
        .annotate(
            priority_group=Case(
                When(unknown, then=Value("unknown")),
                When(expired, then=Value("expired")),
                default=Value("soon"),
                output_field=CharField(),
            )
        )
        .annotate(
            group_rank=Window(
                expression=RowNumber(),
                partition_by=[F("priority_group")],
                order_by=[F("estimated_expires_on").asc(nulls_last=True), F("pk").asc()],
            )
        )
        .filter(group_rank__lte=3)
        .order_by("priority_group", "estimated_expires_on", "pk")
    )
    groups = {"soon": [], "unknown": [], "expired": []}
    for batch in priority:
        batch.days_left = (
            (batch.estimated_expires_on - today).days if batch.estimated_expires_on else None
        )
        groups[batch.priority_group].append(batch)
    history = CookingHistory.objects.filter(user=user)
    count = history.aggregate(total=Count("pk"))["total"]
    recent = list(history.select_related("recipe").order_by("-cooked_at", "-pk")[:3])
    for entry in recent:
        entry.display_time = timezone.localtime(entry.cooked_at, JAKARTA)
    # Next seven days of every saved plan, including plans that start later.
    upcoming = (
        PlannedMeal.objects.filter(
            plan__user=user,
            plan__status="saved",
            scheduled_on__range=(today + timedelta(days=1), today + timedelta(days=7)),
        )
        .select_related("plan", "recipe")
        .order_by("scheduled_on", "plan__title", "pk")
    )
    week = [{"date": today + timedelta(days=offset), "meals": []} for offset in range(1, 8)]
    for meal in upcoming:
        snapshot = meal.snapshot if isinstance(meal.snapshot, dict) else {}
        week[(meal.scheduled_on - today).days - 1]["meals"].append(
            {
                "slot_id": meal.pk,
                "plan_title": meal.plan.title,
                "label": MEALS.get(meal.meal_type, meal.meal_type),
                "order": list(MEALS).index(meal.meal_type) if meal.meal_type in MEALS else 99,
                "name": (snapshot.get("name") or meal.recipe.name)
                + (" + Nasi" if snapshot.get("with_rice") else ""),
                "status": meal.status,
            }
        )
    for day in week:
        day["meals"].sort(key=lambda meal: meal["order"])
    draft = (
        BudgetPlan.objects.filter(user=user, status="draft").select_related("source_plan").first()
    )
    return {
        "today": today,
        "week": week,
        "week_has_meals": any(day["meals"] for day in week),
        "unsaved_draft": draft if draft is not None and not draft_is_clean(draft) else None,
        "plans": plans,
        "stock_counts": stock_counts,
        "stock_groups": groups,
        "cooking_count": count,
        "recent_cooking": recent,
    }
