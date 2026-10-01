"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LogoutView
from django.urls import path
from django.views.generic import TemplateView

from apps.accounts.forms import EmailOrUsernameAuthenticationForm
from apps.accounts.views import AccountLoginView, landing_view, signup_view
from apps.budget_planner.views import planner_page
from apps.pantry.views import (
    delete_pantry_item,
    fallback_receipt_ocr,
    pantry_page,
    save_pantry_items,
    suggest_receipt_items,
    update_pantry_details,
)

urlpatterns = [
    path("", landing_view, name="landing"),
    path("signup/", signup_view, name="signup"),
    path(
        "login/",
        AccountLoginView.as_view(authentication_form=EmailOrUsernameAuthenticationForm),
        name="login",
    ),
    path("logout/", LogoutView.as_view(next_page="landing"), name="logout"),
    path("modul1/", planner_page, name="modul1"),
    path("modul2/", pantry_page, name="modul2"),
    path("modul2/items/", save_pantry_items, name="modul2-items"),
    path("modul2/suggestions/", suggest_receipt_items, name="modul2-suggestions"),
    path("modul2/ocr-fallback/", fallback_receipt_ocr, name="modul2-ocr-fallback"),
    path("modul2/items/<int:item_id>/", update_pantry_details, name="modul2-item-details"),
    path("modul2/items/<int:item_id>/delete/", delete_pantry_item, name="modul2-item-delete"),
    path("modul4/", TemplateView.as_view(template_name="modul4.html"), name="modul4"),
    path(
        "modul5/", login_required(TemplateView.as_view(template_name="modul5.html")), name="modul5"
    ),
    path("admin/", admin.site.urls),
]
