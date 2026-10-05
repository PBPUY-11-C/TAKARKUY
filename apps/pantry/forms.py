from datetime import date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django import forms
from django.utils import timezone

from .models import PantryItem


class StrictTextField(forms.CharField):
    def to_python(self, value):
        if value is not None and not isinstance(value, str):
            raise forms.ValidationError("Nilai harus berupa teks.")
        return super().to_python(value)


class StrictChoiceField(forms.ChoiceField):
    def to_python(self, value):
        if value is not None and not isinstance(value, str):
            raise forms.ValidationError("Pilihan harus berupa teks.")
        return super().to_python(value)


class StrictDateField(forms.DateField):
    def to_python(self, value):
        if value is not None and not isinstance(value, (str, date)):
            raise forms.ValidationError("Tanggal harus berformat YYYY-MM-DD.")
        return super().to_python(value)


class PantryItemForm(forms.Form):
    name = StrictTextField(max_length=255)
    category = StrictChoiceField(choices=PantryItem.CATEGORY_CHOICES)
    quantity = forms.DecimalField(min_value=Decimal("0.000001"), max_digits=14, decimal_places=6)
    unit = StrictChoiceField(choices=PantryItem.UNIT_CHOICES)
    location = StrictChoiceField(choices=PantryItem.LOCATION_CHOICES, required=False)
    shelf_life_days = forms.IntegerField(min_value=1, max_value=3650, required=False)
    starting_on = StrictDateField(required=False, input_formats=["%Y-%m-%d"])
    pack_weight_g = forms.DecimalField(
        min_value=Decimal("0.000001"), max_digits=12, decimal_places=6, required=False
    )
    estimated_expires_on = StrictDateField(required=False, input_formats=["%Y-%m-%d"])
    expiry_source = StrictChoiceField(choices=PantryItem.EXPIRY_CHOICES, required=False)

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if len(name) < 2:
            raise forms.ValidationError("Nama bahan terlalu pendek.")
        return name

    def clean_starting_on(self):
        day = self.cleaned_data["starting_on"]
        if day and day > timezone.localdate(timezone=ZoneInfo("Asia/Jakarta")):
            raise forms.ValidationError("Tanggal belanja tidak boleh di masa depan.")
        if day and day < date(2000, 1, 1):
            raise forms.ValidationError("Tanggal belanja paling awal 1 Januari 2000.")
        return day

    def clean_estimated_expires_on(self):
        day = self.cleaned_data["estimated_expires_on"]
        start = self.cleaned_data.get("starting_on") or timezone.localdate(
            timezone=ZoneInfo("Asia/Jakarta")
        )
        if day and not date(2000, 1, 1) <= day <= start + timedelta(days=3650):
            raise forms.ValidationError(
                "Tanggal kedaluwarsa harus sejak tahun 2000 hingga maksimal 10 tahun dari tanggal belanja."
            )
        return day


class PantryOCRItemForm(PantryItemForm):
    category = StrictChoiceField(choices=PantryItem.CATEGORY_CHOICES, required=False)


class PantryDetailsForm(PantryOCRItemForm):
    quantity = forms.DecimalField(min_value=Decimal(0), max_digits=14, decimal_places=6)
    ingredient_code = StrictTextField(max_length=100, required=False)
    shelf_life_days = forms.IntegerField(min_value=0, max_value=3650, required=False)
    expiry_mode = StrictChoiceField(
        choices=[("auto", "Auto"), ("manual", "Manual")], required=False
    )
