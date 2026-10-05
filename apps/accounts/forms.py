import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from apps.budget_planner.forms import PlannerForm
from apps.catalog.models import Ingredient

from .choices import ALLERGEN_CHOICES


def clean_username(value, *, user=None):
    value = value.strip()
    if user is None or value != user.username:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,30}", value):
            raise forms.ValidationError(
                "Username 3–30 karakter: huruf Latin, angka, titik, garis bawah atau tanda minus; tanpa @."
            )
        value = value.lower()
    users = get_user_model().objects.filter(username__iexact=value)
    if user is not None:
        users = users.exclude(pk=user.pk)
    if users.exists():
        raise forms.ValidationError("Username sudah dipakai.")
    return value


def clean_email(value, *, user=None):
    value = value.strip().lower()
    if not value.isascii():
        raise forms.ValidationError("Gunakan alamat email dengan huruf Latin/ASCII.")
    users = get_user_model().objects
    if user is not None:
        users = users.exclude(pk=user.pk)
    if users.filter(email__iexact=value).exists() or users.filter(username__iexact=value).exists():
        raise forms.ValidationError("Email ini sudah terdaftar. Silakan masuk.")
    return value


class SignUpForm(forms.Form):
    username = forms.CharField(
        max_length=30,
        label="Username",
        widget=forms.TextInput(
            attrs={"autocomplete": "username", "placeholder": "Contoh: penakar_alfredo"}
        ),
    )
    full_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "name",
                "placeholder": "Nama lengkap Anda",
            }
        ),
    )
    email = forms.EmailField(
        max_length=150,
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "placeholder": "contoh@email.com",
            }
        ),
    )
    password1 = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": "Buat kata sandi",
                "aria-describedby": "password-help",
            }
        ),
    )
    password2 = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": "Ketik ulang kata sandi",
            }
        ),
    )

    def clean_full_name(self):
        return " ".join(self.cleaned_data["full_name"].split())

    def clean_email(self):
        return clean_email(self.cleaned_data["email"])

    def clean_username(self):
        return clean_username(self.cleaned_data["username"])

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password1")
        if password and cleaned.get("password2") and password != cleaned["password2"]:
            self.add_error("password2", "Konfirmasi kata sandi tidak cocok.")
        if password and cleaned.get("email"):
            first_name, _, last_name = cleaned.get("full_name", "").partition(" ")
            candidate = get_user_model()(
                username=cleaned.get("username", ""),
                email=cleaned["email"],
                first_name=first_name,
                last_name=last_name,
            )
            try:
                validate_password(password, user=candidate)
            except ValidationError as error:
                self.add_error("password1", error)
        return cleaned

    def save(self):
        if not self.is_valid():
            raise ValueError("Formulir pendaftaran belum valid.")
        first_name, _, last_name = self.cleaned_data["full_name"].partition(" ")
        return get_user_model().objects.create_user(
            username=self.cleaned_data["username"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password1"],
            first_name=first_name,
            last_name=last_name,
        )


class EmailOrUsernameAuthenticationForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "Email/username atau kata sandi salah.",
        "inactive": "Akun ini dinonaktifkan.",
    }
    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "autocomplete": "username",
                "placeholder": "Email atau username",
            }
        )
    )
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "placeholder": "Kata sandi",
            }
        ),
    )

    def clean_username(self):
        identifier = self.cleaned_data["username"].strip()
        return identifier.lower() if "@" in identifier else identifier


class AccountDetailsForm(forms.Form):
    full_name = forms.CharField(max_length=150, label="Nama lengkap")
    username = forms.CharField(max_length=150, label="Username")
    email = forms.EmailField(max_length=150, label="Email")
    current_password = forms.CharField(
        required=False,
        strip=False,
        label="Kata sandi saat ini (wajib untuk mengganti email)",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_username(self):
        return clean_username(self.cleaned_data["username"], user=self.user)

    def clean_email(self):
        email = clean_email(self.cleaned_data["email"], user=self.user)
        if email != self.user.email and not self.user.check_password(
            self.data.get("current_password", "")
        ):
            raise forms.ValidationError("Masukkan kata sandi saat ini untuk mengganti email.")
        return email


class PreferenceForm(forms.Form):
    targets = forms.MultipleChoiceField(
        choices=PlannerForm.TARGET_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label="Target makan",
    )
    meal_types = forms.MultipleChoiceField(
        choices=PlannerForm.MEAL_CHOICES, widget=forms.CheckboxSelectMultiple, label="Waktu makan"
    )
    servings = forms.IntegerField(min_value=1, max_value=10, label="Jumlah orang")
    allergens = forms.MultipleChoiceField(
        choices=ALLERGEN_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Alergi",
    )
    avoided_ingredients = forms.ModelMultipleChoiceField(
        queryset=Ingredient.objects.order_by("name"),
        required=False,
        label="Bahan yang ingin dihindari (bukan alergi)",
        widget=forms.SelectMultiple(attrs={"size": 8}),
    )
    version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)

    def clean_targets(self):
        values = self.cleaned_data["targets"]
        if "seimbang" in values and len(values) > 1:
            raise forms.ValidationError("Seimbang tidak dapat digabung dengan target lain.")
        return values

    def clean_avoided_ingredients(self):
        values = self.cleaned_data["avoided_ingredients"]
        if len(values) > 10 or len(", ".join(row.name for row in values)) > 250:
            raise forms.ValidationError(
                "Pilih maksimal 10 bahan (total nama maksimal 250 karakter)."
            )
        return values
