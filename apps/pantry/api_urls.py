from django.urls import path

from . import api_views

app_name = "pantry_api"

urlpatterns = [
    path("items/", api_views.item_list, name="item_list"),
    path("items/<int:item_id>/", api_views.item_detail, name="item_detail"),
    path("items/<int:item_id>/update/", api_views.item_update, name="item_update"),
    path("items/<int:item_id>/delete/", api_views.item_delete, name="item_delete"),
    path("recipes/", api_views.recipe_ideas, name="recipe_ideas"),
]
