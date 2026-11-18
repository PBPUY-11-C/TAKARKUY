from django.contrib.auth.views import LogoutView
from django.urls import path

from apps.login.forms import EmailOrUsernameAuthenticationForm
from apps.login.views import (
    AccountLoginView,
    food_preferences_view,
    landing_view,
    password_change_view,
    profile_view,
    signup_view,
)

app_name = "login"

urlpatterns = [
    path("", landing_view, name="show_landing"),
    path("signup/", signup_view, name="register"),
    path(
        "login/",
        AccountLoginView.as_view(authentication_form=EmailOrUsernameAuthenticationForm),
        name="login",
    ),
    path("logout/", LogoutView.as_view(next_page="login:show_landing"), name="logout"),
    path("profil/", profile_view, name="show_profile"),
    path("profil/preferensi/", food_preferences_view, name="food_preferences"),
    path("profil/ganti-kata-sandi/", password_change_view, name="change_password"),
]
