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


def landing_view(request):
    if request.user.is_authenticated:
        return redirect("modul5")
    return render(request, "landing.html")


@require_http_methods(["GET", "POST"])
def signup_view(request):
    if request.user.is_authenticated:
        return redirect("modul5")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save()
        except IntegrityError:
            form.add_error(None, "Username atau email sudah terdaftar. Silakan periksa kembali.")
        else:
            login(request, user)
            adopt_guest_result(request)
            return redirect("modul5")
    return render(request, "accounts/signup.html", {"form": form})


class AccountLoginView(LoginView):
    template_name = "accounts/login.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        adopt_guest_result(self.request)
        if not self.request.POST.get("remember_me"):
            self.request.session.set_expiry(0)
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
    preferences = PreferenceForm(
        initial={
            "targets": profile.targets,
            "meal_types": profile.meal_types,
            "servings": profile.servings,
            "allergens": profile.allergens,
            "avoided_ingredients": profile.avoided_ingredients.all(),
            "version": profile.version,
        }
    )
    password = PasswordChangeForm(request.user)
    status = 200
    if request.method == "POST":
        action = request.POST.get("action")
        active = {
            "account": AccountDetailsForm,
            "preferences": PreferenceForm,
            "password": PasswordChangeForm,
        }
        if action not in active:
            response = render(
                request,
                "accounts/profile.html",
                {
                    "account_form": account,
                    "preference_form": preferences,
                    "password_form": password,
                    "error": "Aksi tidak valid.",
                },
                status=400,
            )
            patch_cache_control(response, private=True, no_store=True)
            return response
        if action == "account":
            account = form = AccountDetailsForm(request.POST, user=request.user)
        elif action == "preferences":
            preferences = form = PreferenceForm(request.POST)
        else:
            password = form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # User -> profile is the common lock order with planner operations.
                    locked = get_user_model().objects.select_for_update().get(pk=request.user.pk)
                    current = UserProfile.objects.select_for_update().get(pk=profile.pk)
                    if action != "password" and current.version != form.cleaned_data["version"]:
                        raise ValueError(
                            "Profil berubah di tab lain. Muat ulang sebelum menyimpan."
                        )
                    if action == "account":
                        data = form.cleaned_data
                        if data["email"] != locked.email and not locked.check_password(
                            data["current_password"]
                        ):
                            raise ValueError("Kata sandi saat ini tidak cocok.")
                        first, _, last = " ".join(data["full_name"].split()).partition(" ")
                        locked.first_name, locked.last_name = first, last
                        locked.username, locked.email = data["username"], data["email"]
                        locked.save(update_fields=["first_name", "last_name", "username", "email"])
                    elif action == "preferences":
                        for field in ("targets", "meal_types", "servings", "allergens"):
                            setattr(current, field, form.cleaned_data[field])
                        current.avoided_ingredients.set(form.cleaned_data["avoided_ingredients"])
                    else:
                        password = PasswordChangeForm(locked, request.POST)
                        if not password.is_valid():
                            raise ValueError("Kata sandi berubah. Muat ulang dan coba kembali.")
                        locked = password.save()
                    current.version += 1
                    current.save()
                if action == "password":
                    update_session_auth_hash(request, locked)
                messages.success(request, "Perubahan berhasil disimpan.")
                return redirect("modul3")
            except IntegrityError:
                form.add_error(None, "Username atau email sudah dipakai. Periksa kembali.")
                status = 400
            except ValueError as exc:
                form.add_error(None, str(exc))
                status = 409
        else:
            status = 400
    response = render(
        request,
        "accounts/profile.html",
        {"account_form": account, "preference_form": preferences, "password_form": password},
        status=status,
    )
    patch_cache_control(response, private=True, no_store=True)
    return response
