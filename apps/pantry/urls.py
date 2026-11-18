from django.urls import path

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

app_name = "pantry"

urlpatterns = [
    path("", pantry_page, name="show_pantry"),
    path("items/", save_pantry_items, name="save_items"),
    path("items/<int:item_id>/", update_pantry_details, name="update_item"),
    path("items/<int:item_id>/delete/", delete_pantry_item, name="delete_item"),
    path("items/<int:item_id>/movements/", pantry_movements, name="item_movements"),
    path("suggestions/", suggest_receipt_items, name="suggest_items"),
    path("ocr-fallback/", fallback_receipt_ocr, name="ocr_fallback"),
    path("recipes/", pantry_recipe_matches, name="recipe_matches"),
    path("staples/", save_staple_preferences, name="save_staples"),
]
