from django.urls import path

from . import api_views

app_name = "planner_api"

urlpatterns = [
    path("plans/", api_views.plan_list, name="plan_list"),
    path("plans/<uuid:plan_id>/", api_views.plan_detail, name="plan_detail"),
    path("plans/<uuid:plan_id>/save/", api_views.plan_save, name="plan_save"),
    path("plans/<uuid:plan_id>/delete/", api_views.plan_delete, name="plan_delete"),
]
