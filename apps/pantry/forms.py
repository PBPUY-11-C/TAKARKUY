from decimal import Decimal
from zoneinfo import ZoneInfo

from django import forms
from django.utils import timezone

from .models import PantryItem


class PantryItemForm(forms.Form):
    name = forms.CharField(max_length=255)
    category = forms.ChoiceField(choices=PantryItem.CATEGORY_CHOICES)
    quantity = forms.DecimalField(min_value=Decimal("0.001"), max_digits=10, decimal_places=3)
    unit = forms.ChoiceField(choices=PantryItem.UNIT_CHOICES)
    location = forms.ChoiceField(choices=PantryItem.LOCATION_CHOICES, required=False)
    shelf_life_days = forms.IntegerField(min_value=1, max_value=3650, required=False)
    starting_on = forms.DateField(required=False, input_formats=["%Y-%m-%d"])

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if len(name) < 2:
            raise forms.ValidationError("Nama bahan terlalu pendek.")
        return name

    def clean_starting_on(self):
        day = self.cleaned_data["starting_on"]
        if day and day > timezone.localdate(timezone=ZoneInfo("Asia/Jakarta")):
            raise forms.ValidationError("Tanggal belanja tidak boleh di masa depan.")
        return day


class PantryOCRItemForm(PantryItemForm):
    category = forms.ChoiceField(choices=PantryItem.CATEGORY_CHOICES, required=False)


class PantryDetailsForm(forms.Form):
    location = forms.ChoiceField(choices=PantryItem.LOCATION_CHOICES, required=False)
    estimated_expires_on = forms.DateField(required=False, input_formats=["%Y-%m-%d"])
