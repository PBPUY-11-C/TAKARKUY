from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.budget_planner.services import adopt_guest_result

from .forms import SignUpForm


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
            form.add_error("email", "Email ini sudah terdaftar. Silakan masuk.")
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
