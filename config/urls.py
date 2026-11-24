"""URL configuration for config project."""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

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
    path("api/schema/", SpectacularAPIView.as_view(), name="api_schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="api_schema"), name="api_docs"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="api_schema"), name="api_redoc"),
]
