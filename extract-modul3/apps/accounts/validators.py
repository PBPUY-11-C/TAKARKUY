from django.core.exceptions import ValidationError


class UppercaseNumberSymbolValidator:
    def validate(self, password, user=None):
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
        return "Kata sandi harus mengandung huruf kapital, angka, dan simbol."
