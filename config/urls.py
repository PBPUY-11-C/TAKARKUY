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
]
