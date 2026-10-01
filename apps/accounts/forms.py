from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


class SignUpForm(forms.Form):
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
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": "Buat kata sandi",
                "aria-describedby": "password-help",
            }
        )
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": "Ketik ulang kata sandi",
            }
        )
    )

    def clean_full_name(self):
        return " ".join(self.cleaned_data["full_name"].split())

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        user_model = get_user_model()
        if (
            user_model.objects.filter(email__iexact=email).exists()
            or user_model.objects.filter(username__iexact=email).exists()
        ):
            raise forms.ValidationError("Email ini sudah terdaftar. Silakan masuk.")
        return email

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password1")
        if password and cleaned.get("password2") and password != cleaned["password2"]:
            self.add_error("password2", "Konfirmasi kata sandi tidak cocok.")
        if password and cleaned.get("email"):
            first_name, _, last_name = cleaned.get("full_name", "").partition(" ")
            candidate = get_user_model()(
                username=cleaned["email"],
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
            username=self.cleaned_data["email"],
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
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "placeholder": "Kata sandi",
            }
        )
    )

    def clean_username(self):
        identifier = self.cleaned_data["username"].strip()
        return identifier.lower() if "@" in identifier else identifier
