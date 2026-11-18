from django.urls import path

from apps.home.views import (
    dashboard_page,
    market_lookup,
    my_recipe_create,
    my_recipe_delete,
    my_recipe_detail,
    my_recipe_edit,
)

app_name = "home"

urlpatterns = [
    path("", dashboard_page, name="show_dashboard"),
    path("places/", market_lookup, name="market_lookup"),
    path("resep/tambah/", my_recipe_create, name="create_recipe"),
    path("resep/<int:pk>/", my_recipe_detail, name="show_recipe"),
    path("resep/<int:pk>/edit/", my_recipe_edit, name="edit_recipe"),
    path("resep/<int:pk>/hapus/", my_recipe_delete, name="delete_recipe"),
]
