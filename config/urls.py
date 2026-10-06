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
from django.contrib.auth.views import LogoutView
from django.urls import path

from apps.accounts.forms import EmailOrUsernameAuthenticationForm
from apps.accounts.views import AccountLoginView, landing_view, profile_view, signup_view
from apps.budget_planner.plan_views import (
    apply_plan_preview,
    delete_account_plan,
    preview_plan,
    recipe_alternatives,
    save_account_plan,
)
from apps.budget_planner.views import planner_page
from apps.dashboard.views import dashboard_page, market_lookup
from apps.pantry.views import (
    delete_pantry_item,
    fallback_receipt_ocr,
    pantry_movements,
    pantry_page,
    pantry_recipe_matches,
    save_pantry_items,
    suggest_receipt_items,
    update_pantry_details,
)
from apps.recipe_book.views import (
    book_page,
    cooking_preview,
    recipe_review,
    record_cooking,
    set_favorite,
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
    path("modul3/", profile_view, name="modul3"),
    path("modul1/", planner_page, name="modul1"),
    path("modul1/plans/<uuid:plan_id>/save/", save_account_plan, name="modul1-plan-save"),
    path("modul1/plans/<uuid:plan_id>/delete/", delete_account_plan, name="modul1-plan-delete"),
    path("modul1/plans/<uuid:plan_id>/preview/", preview_plan, name="modul1-plan-preview"),
    path(
        "modul1/plans/<uuid:plan_id>/alternatives/",
        recipe_alternatives,
        name="modul1-plan-alternatives",
    ),
    path(
        "modul1/previews/<uuid:preview_id>/apply/", apply_plan_preview, name="modul1-preview-apply"
    ),
    path("modul2/", pantry_page, name="modul2"),
    path("modul2/items/", save_pantry_items, name="modul2-items"),
    path("modul2/suggestions/", suggest_receipt_items, name="modul2-suggestions"),
    path("modul2/ocr-fallback/", fallback_receipt_ocr, name="modul2-ocr-fallback"),
    path("modul2/items/<int:item_id>/", update_pantry_details, name="modul2-item-details"),
    path("modul2/items/<int:item_id>/delete/", delete_pantry_item, name="modul2-item-delete"),
    path("modul2/items/<int:item_id>/movements/", pantry_movements, name="modul2-item-movements"),
    path("modul2/recipes/", pantry_recipe_matches, name="modul2-recipes"),
    path("modul4/", book_page, name="modul4"),
    path("modul4/favorite/", set_favorite, name="modul4-favorite"),
    path("modul4/preview/", cooking_preview, name="modul4-preview"),
    path("modul4/cook/", record_cooking, name="modul4-cook"),
    path("modul4/review/", recipe_review, name="modul4-review"),
    path("modul5/", dashboard_page, name="modul5"),
    path("modul5/places/", market_lookup, name="modul5-places"),
    path("admin/", admin.site.urls),
]
