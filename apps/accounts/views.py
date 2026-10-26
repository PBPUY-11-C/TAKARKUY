from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.utils.cache import patch_cache_control
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from .forms import AccountDetailsForm, PreferenceForm, SignUpForm
from .models import UserProfile
from .preferences import preferences_for, profile_for


def landing_menu():
    """Halal recipes with a one-serving price, grouped per meal for the landing preview."""
    from apps.catalog.models import Recipe
    from apps.recipe_book.services import recipe_costs

    recipes = Recipe.objects.filter(
        is_active=True, is_plannable=True, recipetag__tag="halal"
    ).distinct()
    names = {recipe.pk: (recipe.meal_type, recipe.name) for recipe in recipes}
    menu = {}
    for code, cost in recipe_costs(1, set(names)).items():
        meal, name = names[code]
        menu.setdefault(meal, []).append([round(cost), name])
    for items in menu.values():
        items.sort()
    return menu


def landing_view(request):
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)
    from apps.catalog.models import Recipe

    return render(request, "landing.html", {
        # Pricing every recipe takes ~1 s, so share one result across visitors.
        "landing_menu": cache.get_or_set("landing-menu", landing_menu, 3600),
        "recipe_count": Recipe.objects.filter(is_active=True, is_plannable=True).count(),
    })


@require_http_methods(["GET", "POST"])
def signup_view(request):
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)
    form = SignUpForm(request.POST or None)
    # Same-site "next" only, as LoginView does, so signing up can return to the planner.
    next_url = request.POST.get("next") or request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = ""
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
            return redirect(next_url or settings.LOGIN_REDIRECT_URL)
    return render(request, "accounts/signup.html", {"form": form, "next": next_url})


class AccountLoginView(LoginView):
    template_name = "accounts/login.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.session.set_expiry(None if self.request.POST.get("remember_me") else 0)
        return response


@login_required
@require_http_methods(["GET", "POST"])
def profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    food = preferences_for(request.user)
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
            "targets": food.targets,
            "meal_types": food.meal_types,
            "servings": food.servings,
            "allergens": food.allergens,
            "halal_only": "yes" if food.halal_only else "no",
            "avoided_ingredients": food.avoided_ingredients.all(),
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
                        food = preferences_for(locked)
                        for field in ("targets", "meal_types", "servings", "allergens", "halal_only"):
                            setattr(food, field, form.cleaned_data[field])
                        food.save()
                        food.avoided_ingredients.set(form.cleaned_data["avoided_ingredients"])
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
