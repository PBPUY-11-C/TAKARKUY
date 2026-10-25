"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LogoutView
from django.urls import path
from django.views.generic import TemplateView

from apps.accounts.forms import EmailOrUsernameAuthenticationForm
from apps.accounts.views import AccountLoginView, landing_view, profile_view, signup_view

from apps.budget_planner.plan_views import (
    add_plan_purchases,
    apply_plan_preview,
    delete_account_plan,
    preview_plan,
    recipe_alternatives,
    save_account_plan,
)
from apps.budget_planner.views import planner_page
from apps.dashboard.views import dashboard_page, market_lookup
from apps.pantry.views import (
    pantry_page,
    delete_pantry_item,
    fallback_receipt_ocr,
    pantry_movements,
    pantry_recipe_matches,
    save_staple_preferences,
    save_pantry_items,
    suggest_receipt_items,
    update_pantry_details,
)
from apps.recipe_book.views import (
    book_page,
    cooking_preview,
    estimate_recipe_cost,
    recipe_review,
    recipe_review_photo,
    recipe_review_photo_delete,
    recipe_review_photo_file,
    report_recipe_data,
    record_cooking,
    save_recipe_note,
    set_favorite,
    set_slot_status,
)

# Modul 1 and Modul 3 are active. Other module pages remain placeholders;
# their backend endpoints are reused by the planner.
kosong = login_required(TemplateView.as_view(template_name="kosong.html"))

urlpatterns = [
    path("", landing_view, name="landing"),
    path("signup/", signup_view, name="signup"),
    path(
        "login/",
        AccountLoginView.as_view(authentication_form=EmailOrUsernameAuthenticationForm),
        name="login",
    ),
    path("logout/", LogoutView.as_view(next_page="landing"), name="logout"),
    path("modul3/", profile_view, name="modul3"),
    path("planner/", planner_page, name="modul1"),
    path("planner/", planner_page, name="planner"),
    path("modul1/", planner_page),
    path("planner/plans/<uuid:plan_id>/save/", save_account_plan, name="modul1-plan-save"),
    path("planner/plans/<uuid:plan_id>/delete/", delete_account_plan, name="modul1-plan-delete"),
    path("planner/plans/<uuid:plan_id>/pantry/", add_plan_purchases, name="modul1-plan-pantry"),
    path("planner/plans/<uuid:plan_id>/preview/", preview_plan, name="modul1-plan-preview"),
    path(
        "planner/plans/<uuid:plan_id>/alternatives/",
        recipe_alternatives,
        name="modul1-plan-alternatives",
    ),
    path(
        "planner/previews/<uuid:preview_id>/apply/", apply_plan_preview, name="modul1-preview-apply"
    ),
    path("modul2/", pantry_page, name="modul2"),
    path("modul2/items/", save_pantry_items, name="modul2-items"),
    path("modul2/suggestions/", suggest_receipt_items, name="modul2-suggestions"),
    path("modul2/ocr-fallback/", fallback_receipt_ocr, name="modul2-ocr-fallback"),
    path("modul2/items/<int:item_id>/", update_pantry_details, name="modul2-item-details"),
    path("modul2/items/<int:item_id>/delete/", delete_pantry_item, name="modul2-item-delete"),
    path("modul2/items/<int:item_id>/movements/", pantry_movements, name="modul2-item-movements"),
    path("modul2/recipes/", pantry_recipe_matches, name="modul2-recipes"),
    path("modul2/staples/", save_staple_preferences, name="modul2-staples"),
    path("pantry/", pantry_page, name="modul2"),
    path("pantry/items/", save_pantry_items, name="modul2-items"),
    path("pantry/suggestions/", suggest_receipt_items, name="modul2-suggestions"),
    path("pantry/ocr-fallback/", fallback_receipt_ocr, name="modul2-ocr-fallback"),
    path("pantry/items/<int:item_id>/", update_pantry_details, name="modul2-item-details"),
    path("pantry/items/<int:item_id>/delete/", delete_pantry_item, name="modul2-item-delete"),
    path("pantry/items/<int:item_id>/movements/", pantry_movements, name="modul2-item-movements"),
    path("pantry/recipes/", pantry_recipe_matches, name="modul2-recipes"),
    path("modul4/", book_page, name="modul4"),

    path("modul4/favorite/", set_favorite, name="modul4-favorite"),
    path("modul4/note/", save_recipe_note, name="modul4-note"),
    path("modul4/estimate/", estimate_recipe_cost, name="modul4-estimate"),
    path("modul4/preview/", cooking_preview, name="modul4-preview"),
    path("modul4/cook/", record_cooking, name="modul4-cook"),
    path("modul4/report-data/", report_recipe_data, name="modul4-report-data"),
    path("modul4/review/", recipe_review, name="modul4-review"),
    path("modul4/review/photo/", recipe_review_photo, name="modul4-review-photo-upload"),
    path("modul4/review/photo/delete/", recipe_review_photo_delete, name="modul4-review-photo-delete"),
    path("modul4/reviews/<int:review_id>/photo/", recipe_review_photo_file, name="modul4-review-photo"),
    path("modul4/slot-status/", set_slot_status, name="modul4-slot-status"),
    path("modul5/", dashboard_page, name="modul5"),
    path("modul5/places/", market_lookup, name="modul5-places"),
    path("admin/", admin.site.urls),
]
