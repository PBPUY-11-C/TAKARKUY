"""URL configuration for config project."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.login.urls")),
    path("planner/", include("apps.planner.urls")),
    path("pantry/", include("apps.pantry.urls")),
    path("recipes/", include("apps.recipe.urls")),
    path("dashboard/", include("apps.home.urls")),
    path("api/planner/", include("apps.planner.api_urls")),
    path("api/auth/", include("apps.login.api_urls")),
    path("api/pantry/", include("apps.pantry.api_urls")),
    path("api/recipes/", include("apps.recipe.api_urls")),
    path("api/dashboard/", include("apps.home.api_urls")),
]
