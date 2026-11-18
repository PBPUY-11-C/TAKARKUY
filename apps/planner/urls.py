from django.urls import path

from apps.planner.plan_views import (
    add_plan_purchases,
    apply_plan_preview,
    delete_account_plan,
    preview_plan,
    recipe_alternatives,
    save_account_plan,
    shopping_list_download,
)
from apps.planner.views import planner_page

app_name = "planner"

urlpatterns = [
    path("", planner_page, name="show_planner"),
    path("plans/<uuid:plan_id>/save/", save_account_plan, name="save_plan"),
    path("plans/<uuid:plan_id>/delete/", delete_account_plan, name="delete_plan"),
    path("plans/<uuid:plan_id>/pantry/", add_plan_purchases, name="add_to_pantry"),
    path("plans/<uuid:plan_id>/preview/", preview_plan, name="preview_plan"),
    path(
        "plans/<uuid:plan_id>/alternatives/", recipe_alternatives, name="recipe_alternatives"
    ),
    path(
        "plans/<uuid:plan_id>/belanja.pdf",
        shopping_list_download,
        name="download_shopping_list",
    ),
    path("previews/<uuid:preview_id>/apply/", apply_plan_preview, name="apply_preview"),
]
