from django.urls import path

from . import api_views

app_name = "recipe_api"

urlpatterns = [
    path("", api_views.recipe_list, name="recipe_list"),
    path("favorites/", api_views.favorites, name="favorites"),
    path("notes/", api_views.save_note, name="save_note"),
    path("history/", api_views.cooking_history, name="history"),
    path("cook/preview/", api_views.cooking_preview, name="cooking_preview"),
    path("cook/", api_views.record_cooking, name="record_cooking"),
    # Paling akhir agar path tetap di atas tidak tertangkap sebagai kode resep.
    path("<str:code>/", api_views.recipe_detail, name="recipe_detail"),
]
