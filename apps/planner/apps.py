from django.apps import AppConfig


class PlannerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.planner"
    label = "budget_planner"  # database label from before the rename
