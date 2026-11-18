from django.urls import path

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

app_name = "recipe"

urlpatterns = [
    path("", book_page, name="show_recipes"),
    path("favorite/", set_favorite, name="set_favorite"),
    path("note/", save_recipe_note, name="save_note"),
    path("estimate/", estimate_recipe_cost, name="estimate_cost"),
    path("preview/", cooking_preview, name="cooking_preview"),
    path("cook/", record_cooking, name="record_cooking"),
    path("slot-status/", set_slot_status, name="set_slot_status"),
    path("report-data/", report_recipe_data, name="report_data"),
    path("review/", recipe_review, name="save_review"),
    path("review/photo/", recipe_review_photo, name="upload_review_photo"),
    path("review/photo/delete/", recipe_review_photo_delete, name="delete_review_photo"),
    path("reviews/<int:review_id>/photo/", recipe_review_photo_file, name="show_review_photo"),
]
