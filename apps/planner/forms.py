from decimal import Decimal

from django import forms

from apps.login.choices import ALLERGEN_CHOICES


class PlannerForm(forms.Form):
    halal_only = forms.BooleanField(required=False, initial=True, widget=forms.HiddenInput)

    def clean_halal_only(self):
        return self.cleaned_data["halal_only"] if "halal_only" in self.data else True

    allergens = forms.MultipleChoiceField(
        choices=ALLERGEN_CHOICES, required=False, widget=forms.MultipleHiddenInput
    )
    MEAL_CHOICES = [
        ("sarapan", "Pagi"),
        ("makan_siang", "Siang"),
        ("makan_malam", "Malam"),
    ]
    TARGET_CHOICES = [
        ("seimbang", "Seimbang"),
        ("tinggi_protein", "Tinggi protein"),
        ("rendah_kalori", "Rendah kalori"),
    ]
    budget = forms.CharField(
        label="Budget",
        widget=forms.TextInput(
            attrs={"inputmode": "numeric", "autocomplete": "off", "class": "js-rupiah-input"}
        ),
    )
    days = forms.IntegerField(
        label="Hari",
        min_value=1,
        max_value=7,
        widget=forms.NumberInput(
            attrs={"min": "1", "max": "7", "step": "1", "inputmode": "numeric"}
        ),
        error_messages={
            "min_value": "Minimal 1 hari.",
            "max_value": "Maksimal 7 hari.",
            "invalid": "Masukkan jumlah hari berupa angka bulat.",
        },
    )
    servings = forms.IntegerField(
        label="Orang",
        min_value=1,
        max_value=10,
        widget=forms.NumberInput(
            attrs={"min": "1", "max": "10", "step": "1", "inputmode": "numeric"}
        ),
        error_messages={
            "min_value": "Minimal 1 orang.",
            "max_value": "Maksimal 10 orang.",
            "invalid": "Masukkan jumlah orang berupa angka bulat.",
        },
    )
    meal_types = forms.MultipleChoiceField(
        label="Waktu makan",
        choices=MEAL_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Pilih minimal satu waktu makan."},
    )
    targets = forms.MultipleChoiceField(
        label="Target gizi",
        choices=TARGET_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Pilih minimal satu target gizi."},
    )
    exclude_ingredients = forms.CharField(
        label="Bahan dihindari",
        required=False,
        max_length=250,
        widget=forms.TextInput(
            attrs={"placeholder": "Contoh: udang, telur, kacang", "autocomplete": "off"}
        ),
    )

    STAPLE_CHOICES = [
        ("nasi", "Nasi"),
        ("kentang", "Kentang"),
        ("ubi", "Ubi"),
        ("singkong", "Singkong"),
        ("jagung", "Jagung"),
        ("no", "Tanpa"),
    ]
    LEGACY_RICE_CHOICES = [("auto", "Nasi (otomatis 1–2 orang)"), ("yes", "Nasi")]
    rice = forms.ChoiceField(
        label="Karbohidrat",
        choices=STAPLE_CHOICES + LEGACY_RICE_CHOICES,
        required=False,
        initial="nasi",
    )

    def clean_rice(self):
        return self.cleaned_data["rice"] or "no"

    def clean_targets(self):
        targets = self.cleaned_data["targets"]
        if "seimbang" in targets and len(targets) > 1:
            raise forms.ValidationError("Seimbang tidak bisa digabung dengan target gizi lain.")
        return targets

    def clean_exclude_ingredients(self):
        terms = [
            part.strip().casefold() for part in self.cleaned_data["exclude_ingredients"].split(",")
        ]
        terms = list(dict.fromkeys(term for term in terms if term))
        if len(terms) > 10:
            raise forms.ValidationError("Maksimal 10 nama bahan, pisahkan dengan koma.")
        return terms

    def clean_budget(self):
        raw = str(self.cleaned_data["budget"]).strip()
        if "," in raw:
            raise forms.ValidationError("Tulis tanpa koma atau sen, misalnya 150.000.")
        normalized = raw.replace("Rp", "").replace("rp", "").replace(".", "").replace(" ", "")
        if not normalized.isascii() or not normalized.isdigit():
            raise forms.ValidationError("Masukkan nominal rupiah dengan angka, misalnya 10.000.")
        amount = Decimal(normalized)
        if amount < 1:
            raise forms.ValidationError("Minimal budget Rp 1.")
        if amount > Decimal("100000000"):
            raise forms.ValidationError("Maksimal budget Rp 100.000.000.")
        return amount


class PlanMetadataForm(forms.Form):
    """Title and start date chosen when saving; a missing date keeps the current one."""

    title = forms.CharField(
        label="Judul",
        max_length=100,
        error_messages={
            "required": "Isi judul rencana.",
            "max_length": "Judul maksimal 100 karakter.",
        },
    )
    starts_on = forms.DateField(
        label="Tanggal mulai",
        required=False,
        error_messages={"invalid": "Format tanggal mulai tidak valid."},
    )

    def clean_title(self):
        return " ".join(self.cleaned_data["title"].split())
