from django.urls import path

from . import api_views

app_name = "home_api"

urlpatterns = [
    path("summary/", api_views.dashboard_summary, name="summary"),
    path("recipes/", api_views.recipe_list, name="recipe_list"),
    path("recipes/<int:pk>/", api_views.recipe_detail, name="recipe_detail"),
    path("recipes/<int:pk>/update/", api_views.recipe_update, name="recipe_update"),
    path("recipes/<int:pk>/delete/", api_views.recipe_delete, name="recipe_delete"),
    path("markets/", api_views.market_list, name="market_list"),
]
