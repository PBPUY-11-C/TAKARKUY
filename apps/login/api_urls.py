from django.urls import path

from . import api_views

app_name = "auth_api"

urlpatterns = [
    path("login/", api_views.login_view, name="login"),
    path("logout/", api_views.logout_view, name="logout"),
    path("register/", api_views.register_view, name="register"),
    path("profile/", api_views.profile_view, name="profile"),
    path("profile/update/", api_views.profile_update, name="profile_update"),
    path("preferences/update/", api_views.preferences_update, name="preferences_update"),
    path("password/", api_views.password_change, name="change_password"),
]
