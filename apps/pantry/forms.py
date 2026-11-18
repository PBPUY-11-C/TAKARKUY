from datetime import date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django import forms
from django.utils import timezone

from apps.recipe.staples import STAPLE_GROUPS

from .models import PantryItem


class StaplePreferenceForm(forms.Form):
    """Form pilihan bahan pokok yang dilacak, dengan version untuk mencegah tulisan saling timpa."""

    tracked_staples = forms.MultipleChoiceField(
        choices=[(key, label) for key, label, _codes in STAPLE_GROUPS],
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    version = forms.IntegerField(min_value=1)


class StrictTextField(forms.CharField):
    """CharField yang menolak nilai JSON non-string (angka, list, dll) alih-alih mengonversinya."""

    def to_python(self, value):
        """Memvalidasi bahwa nilai berupa string sebelum diproses CharField."""
        if value is not None and not isinstance(value, str):
            raise forms.ValidationError("Nilai harus berupa teks.")
        return super().to_python(value)


class StrictChoiceField(forms.ChoiceField):
    """ChoiceField yang hanya menerima string agar nilai JSON non-teks tidak lolos konversi."""

    def to_python(self, value):
        """Memvalidasi bahwa pilihan berupa string sebelum diproses ChoiceField."""
        if value is not None and not isinstance(value, str):
            raise forms.ValidationError("Pilihan harus berupa teks.")
        return super().to_python(value)


class StrictDateField(forms.DateField):
    """DateField yang hanya menerima string atau objek date."""

    def to_python(self, value):
        """Menolak tipe selain string/date sebelum diparse sebagai tanggal."""
        if value is not None and not isinstance(value, (str, date)):
            raise forms.ValidationError("Tanggal harus berformat YYYY-MM-DD.")
        return super().to_python(value)


class PantryItemForm(forms.Form):
    """Validasi satu item stok baru: nama, kategori, jumlah, satuan, lokasi, data kedaluwarsa."""

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
        """Merapikan spasi berlebih pada nama dan menolak nama kurang dari 2 karakter."""
        name = " ".join(self.cleaned_data["name"].split())
        if len(name) < 2:
            raise forms.ValidationError("Nama bahan terlalu pendek.")
        return name

    def clean_starting_on(self):
        """Tanggal belanja tidak boleh setelah hari ini (WIB) atau sebelum 1 Januari 2000."""
        day = self.cleaned_data["starting_on"]
        if day and day > timezone.localdate(timezone=ZoneInfo("Asia/Jakarta")):
            raise forms.ValidationError("Tanggal belanja tidak boleh di masa depan.")
        if day and day < date(2000, 1, 1):
            raise forms.ValidationError("Tanggal belanja paling awal 1 Januari 2000.")
        return day

    def clean_estimated_expires_on(self):
        """Tanggal kedaluwarsa harus sejak 2000 dan paling lambat 10 tahun dari tanggal belanja.

        Bila tanggal belanja kosong, hari ini (WIB) dipakai sebagai acuan.
        """
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
    """Varian form item untuk hasil OCR struk, kategori boleh kosong."""

    category = StrictChoiceField(choices=PantryItem.CATEGORY_CHOICES, required=False)


class PantryDetailsForm(PantryOCRItemForm):
    """Form edit detail item: jumlah dan masa simpan boleh 0, plus kode bahan dan expiry_mode."""

    quantity = forms.DecimalField(min_value=Decimal(0), max_digits=14, decimal_places=6)
    ingredient_code = StrictTextField(max_length=100, required=False)
    shelf_life_days = forms.IntegerField(min_value=0, max_value=3650, required=False)
    expiry_mode = StrictChoiceField(
        choices=[("auto", "Auto"), ("manual", "Manual")], required=False
    )
