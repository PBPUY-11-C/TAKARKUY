from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.utils.cache import patch_cache_control
from django.views.decorators.http import require_http_methods

from apps.budget_planner.services import adopt_guest_result

from .forms import AccountDetailsForm, PreferenceForm, SignUpForm
from .models import UserProfile
from .preferences import preferences_for, profile_for


def landing_view(request):
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)
    return render(request, "landing.html")


@require_http_methods(["GET", "POST"])
def signup_view(request):
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)
    form = SignUpForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save()
                profile_for(user)
                preferences_for(user)
        except IntegrityError:
            form.add_error(None, "Username atau email sudah terdaftar. Silakan periksa kembali.")
        else:
            login(request, user)
            adopt_guest_result(request)
            return redirect(settings.LOGIN_REDIRECT_URL)
    return render(request, "accounts/signup.html", {"form": form})


class AccountLoginView(LoginView):
    template_name = "accounts/login.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        adopt_guest_result(self.request)
        self.request.session.set_expiry(None if self.request.POST.get("remember_me") else 0)
        return response


@login_required
@require_http_methods(["GET", "POST"])
def profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    account = AccountDetailsForm(
        user=request.user,
        initial={
            "full_name": request.user.get_full_name() or request.user.username,
            "username": request.user.username,
            "email": request.user.email,
            "version": profile.version,
        },
    )
    status, error = 200, None
    if request.method == "POST":
        if request.POST.get("action") != "account":
            status, error = 400, "Aksi tidak valid."
        else:
            account = AccountDetailsForm(request.POST, user=request.user)
            if account.is_valid():
                try:
                    with transaction.atomic():
                        locked = get_user_model().objects.select_for_update().get(pk=request.user.pk)
                        current = UserProfile.objects.select_for_update().get(pk=profile.pk)
                        if current.version != account.cleaned_data["version"]:
                            raise ValueError("Profil berubah di tab lain. Muat ulang sebelum menyimpan.")
                        data = account.cleaned_data
                        if data["email"] != locked.email and not locked.check_password(
                            data["current_password"]
                        ):
                            raise ValueError("Kata sandi saat ini tidak cocok.")
                        first, _, last = " ".join(data["full_name"].split()).partition(" ")
                        locked.first_name, locked.last_name = first, last
                        locked.username, locked.email = data["username"], data["email"]
                        locked.save(update_fields=["first_name", "last_name", "username", "email"])
                        current.version += 1
                        current.save(update_fields=["version"])
                    messages.success(request, "Perubahan berhasil disimpan.")
                    return redirect("modul3")
                except IntegrityError:
                    account.add_error(None, "Username atau email sudah dipakai. Periksa kembali.")
                    status = 400
                except ValueError as exc:
                    account.add_error(None, str(exc))
                    status = 409
            else:
                status = 400
    response = render(
        request, "accounts/profile.html", {"account_form": account, "error": error}, status=status
    )
    patch_cache_control(response, private=True, no_store=True)
    return response


@login_required
@require_http_methods(["GET", "POST"])
def food_preferences_view(request):
    profile = profile_for(request.user)
    food = preferences_for(request.user)
    form = PreferenceForm(
        request.POST if request.method == "POST" else None,
        initial={
            "targets": food.targets,
            "meal_types": food.meal_types,
            "servings": food.servings,
            "allergens": food.allergens,
            "avoided_ingredients": food.avoided_ingredients.all(),
            "version": profile.version,
        },
    )
    status = 200
    if request.method == "POST":
        if form.is_valid():
            try:
                with transaction.atomic():
                    locked = get_user_model().objects.select_for_update().get(pk=request.user.pk)
                    current = UserProfile.objects.select_for_update().get(pk=profile.pk)
                    if current.version != form.cleaned_data["version"]:
                        raise ValueError("Profil berubah di tab lain. Muat ulang sebelum menyimpan.")
                    food = preferences_for(locked)
                    for field in ("targets", "meal_types", "servings", "allergens"):
                        setattr(food, field, form.cleaned_data[field])
                    food.halal_only = True
                    food.save()
                    food.avoided_ingredients.set(form.cleaned_data["avoided_ingredients"])
                    current.version += 1
                    current.save(update_fields=["version"])
                messages.success(request, "Perubahan berhasil disimpan.")
                return redirect("food-preferences")
            except IntegrityError:
                form.add_error(None, "Preferensi belum bisa disimpan. Muat ulang dan coba kembali.")
                status = 400
            except ValueError as exc:
                form.add_error(None, str(exc))
                status = 409
        else:
            status = 400
    response = render(
        request, "accounts/food_preferences.html", {"preference_form": form}, status=status
    )
    patch_cache_control(response, private=True, no_store=True)
    return response


@login_required
@require_http_methods(["GET", "POST"])
def password_change_view(request):
    form = PasswordChangeForm(request.user)
    status = 200
    if request.method == "POST":
        with transaction.atomic():
            # Validate the current password against the locked account, not a stale request user.
            locked = get_user_model().objects.select_for_update().get(pk=request.user.pk)
            form = PasswordChangeForm(locked, request.POST)
            if form.is_valid():
                user = form.save()
                profile, _ = UserProfile.objects.select_for_update().get_or_create(user=locked)
                profile.version += 1
                profile.save(update_fields=["version"])
            else:
                status = 400
        if status == 200:
            update_session_auth_hash(request, user)
            messages.success(request, "Kata sandi berhasil diperbarui.")
            return redirect("modul3")
    response = render(request, "accounts/password_change.html", {"password_form": form}, status=status)
    patch_cache_control(response, private=True, no_store=True)
    return response
