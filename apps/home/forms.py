from django import forms

from .models import MyRecipe


class MyRecipeForm(forms.ModelForm):
    class Meta:
        model = MyRecipe
        fields = ["nama", "waktu_makan", "porsi", "bahan", "langkah", "estimasi_harga"]
        labels = {
            "nama": "Nama resep",
            "waktu_makan": "Waktu makan",
            "porsi": "Porsi",
            "bahan": "Bahan (satu per baris)",
            "langkah": "Cara memasak (satu langkah per baris)",
            "estimasi_harga": "Estimasi harga (Rp, opsional)",
        }
        widgets = {
            "nama": forms.TextInput(attrs={"placeholder": "Contoh: Sayur sop ibu"}),
            "bahan": forms.Textarea(attrs={"rows": 5, "placeholder": "200 gr ayam\n2 buah wortel\n3 siung bawang putih"}),
            "langkah": forms.Textarea(attrs={"rows": 6, "placeholder": "Rebus ayam hingga matang\nMasukkan wortel"}),
        }