from django.core.exceptions import ValidationError


class UppercaseNumberSymbolValidator:
    """Validator kata sandi Django yang mewajibkan huruf kapital, angka, dan simbol."""

    def validate(self, password, user=None):
        """Lempar ValidationError bila kata sandi tidak punya huruf kapital, angka, atau simbol
        (karakter non-alfanumerik selain spasi)."""
        if not (
            any(character.isupper() for character in password)
            and any(character.isdigit() for character in password)
            and any(not character.isalnum() and not character.isspace() for character in password)
        ):
            raise ValidationError(
                "Kata sandi harus mengandung huruf kapital, angka, dan simbol.",
                code="password_missing_required_characters",
            )

    def get_help_text(self):
        """Teks bantuan aturan kata sandi untuk ditampilkan di form."""
        return "Kata sandi harus mengandung huruf kapital, angka, dan simbol."
