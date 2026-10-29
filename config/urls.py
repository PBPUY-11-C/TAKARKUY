"""URL configuration for config project."""

from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import path
from django.views.generic import RedirectView

from apps.home.views import (
    dashboard_page,
    market_lookup,
    my_recipe_create,
    my_recipe_detail,
)
from apps.login.forms import EmailOrUsernameAuthenticationForm
from apps.login.views import (
    AccountLoginView,
    food_preferences_view,
    landing_view,
    password_change_view,
    profile_view,
    signup_view,
)
from apps.pantry.views import (
    delete_pantry_item,
    fallback_receipt_ocr,
    pantry_movements,
    pantry_page,
    pantry_recipe_matches,
    save_pantry_items,
    save_staple_preferences,
    suggest_receipt_items,
    update_pantry_details,
)
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
from apps.recipe.views import (
    book_page,
    cooking_preview,
    estimate_recipe_cost,
    recipe_review,
    recipe_review_photo,
    recipe_review_photo_delete,
    recipe_review_photo_file,
    record_cooking,
    report_recipe_data,
    save_recipe_note,
    set_favorite,
    set_slot_status,
)

urlpatterns = [
    path("", landing_view, name="landing"),
    path("signup/", signup_view, name="signup"),
    path(
        "login/",
        AccountLoginView.as_view(authentication_form=EmailOrUsernameAuthenticationForm),
        name="login",
    ),
    path("logout/", LogoutView.as_view(next_page="landing"), name="logout"),
    path("profil/", profile_view, name="modul3"),
    path("profil/preferensi/", food_preferences_view, name="food-preferences"),
    path("profil/ganti-kata-sandi/", password_change_view, name="password-change"),
    path("modul3/", RedirectView.as_view(pattern_name="modul3", query_string=True)),
    path("planner/", planner_page, name="modul1"),
    path("planner/", planner_page, name="planner"),
    path("modul1/", planner_page),
    path("planner/plans/<uuid:plan_id>/save/", save_account_plan, name="modul1-plan-save"),
    path("planner/plans/<uuid:plan_id>/delete/", delete_account_plan, name="modul1-plan-delete"),
    path("planner/plans/<uuid:plan_id>/pantry/", add_plan_purchases, name="modul1-plan-pantry"),
    path("planner/plans/<uuid:plan_id>/preview/", preview_plan, name="modul1-plan-preview"),
    path(
        "planner/plans/<uuid:plan_id>/belanja.pdf",
        shopping_list_download,
        name="modul1-plan-pdf",
    ),
    path(
        "planner/plans/<uuid:plan_id>/alternatives/",
        recipe_alternatives,
        name="modul1-plan-alternatives",
    ),
    path(
        "planner/previews/<uuid:preview_id>/apply/", apply_plan_preview, name="modul1-preview-apply"
    ),

    path("pantry/", pantry_page, name="modul2"),
    path("pantry/items/", save_pantry_items, name="modul2-items"),
    path("pantry/suggestions/", suggest_receipt_items, name="modul2-suggestions"),
    path("pantry/ocr-fallback/", fallback_receipt_ocr, name="modul2-ocr-fallback"),
    path("pantry/items/<int:item_id>/", update_pantry_details, name="modul2-item-details"),
    path("pantry/items/<int:item_id>/delete/", delete_pantry_item, name="modul2-item-delete"),
    path("pantry/items/<int:item_id>/movements/", pantry_movements, name="modul2-item-movements"),
    path("pantry/recipes/", pantry_recipe_matches, name="modul2-recipes"),
    path("pantry/staples/", save_staple_preferences, name="modul2-staples"),

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
    path("modul5/resep/tambah/", my_recipe_create, name="modul5-recipe-create"),
    path("modul5/resep/<int:pk>/", my_recipe_detail, name="modul5-recipe-detail"),

    path("admin/", admin.site.urls),
]
