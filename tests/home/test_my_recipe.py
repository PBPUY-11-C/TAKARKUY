from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import MyRecipe

User = get_user_model()

DATA_VALID = {
    "nama": "Nasi goreng telur",
    "waktu_makan": "pagi",
    "porsi": 2,
    "bahan": "Nasi\nTelur\nBawang putih",
    "langkah": "Tumis bawang\nMasukkan nasi",
    "estimasi_harga": 15000,
}


def buat_resep(user, **kwargs):
    data = {**DATA_VALID, **kwargs}
    return MyRecipe.objects.create(user=user, **data)


class MyRecipeModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="aiko", password="rahasia123")

    def test_daftar_bahan_dan_langkah(self):
        resep = buat_resep(self.user)
        self.assertEqual(resep.daftar_bahan(), ["Nasi", "Telur", "Bawang putih"])
        self.assertEqual(resep.daftar_langkah(), ["Tumis bawang", "Masukkan nasi"])


class MyRecipeCrudTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="aiko", password="rahasia123")
        self.lain = User.objects.create_user(username="budi", password="rahasia123")
        self.client.login(username="aiko", password="rahasia123")

    # ---------- Create ----------
    def test_form_tambah_bisa_dibuka(self):
        res = self.client.get(reverse("modul5-recipe-create"))
        self.assertEqual(res.status_code, 200)

    def test_tambah_resep_valid(self):
        res = self.client.post(reverse("modul5-recipe-create"), DATA_VALID)
        self.assertEqual(res.status_code, 302)
        resep = MyRecipe.objects.get()
        self.assertEqual(resep.user, self.user)
        self.assertEqual(resep.nama, "Nasi goreng telur")

    def test_tambah_resep_tidak_valid(self):
        data = {**DATA_VALID, "nama": ""}
        res = self.client.post(reverse("modul5-recipe-create"), data)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(MyRecipe.objects.count(), 0)

    def test_porsi_di_luar_batas_ditolak(self):
        data = {**DATA_VALID, "porsi": 11}
        self.client.post(reverse("modul5-recipe-create"), data)
        self.assertEqual(MyRecipe.objects.count(), 0)

    # ---------- Read ----------
    def test_detail_pemilik_bisa_lihat(self):
        resep = buat_resep(self.user)
        res = self.client.get(reverse("modul5-recipe-detail", args=[resep.pk]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Nasi goreng telur")

    def test_detail_resep_user_lain_404(self):
        resep = buat_resep(self.lain)
        res = self.client.get(reverse("modul5-recipe-detail", args=[resep.pk]))
        self.assertEqual(res.status_code, 404)

    def test_dashboard_menampilkan_resep_saya(self):
        buat_resep(self.user, nama="Soto ayam")
        res = self.client.get(reverse("modul5"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Soto ayam")
        self.assertEqual(res.context["my_recipe_count"], 1)

    def test_dashboard_tidak_menampilkan_resep_user_lain(self):
        buat_resep(self.lain, nama="Rahasia budi")
        res = self.client.get(reverse("modul5"))
        self.assertNotContains(res, "Rahasia budi")
        self.assertEqual(res.context["my_recipe_count"], 0)

    # ---------- Update ----------
    def test_form_edit_bisa_dibuka(self):
        resep = buat_resep(self.user)
        res = self.client.get(reverse("modul5-recipe-edit", args=[resep.pk]))
        self.assertEqual(res.status_code, 200)

    def test_edit_resep(self):
        resep = buat_resep(self.user)
        data = {**DATA_VALID, "nama": "Nasi goreng spesial", "porsi": 4}
        res = self.client.post(reverse("modul5-recipe-edit", args=[resep.pk]), data)
        self.assertEqual(res.status_code, 302)
        resep.refresh_from_db()
        self.assertEqual(resep.nama, "Nasi goreng spesial")
        self.assertEqual(resep.porsi, 4)

    def test_edit_resep_user_lain_404(self):
        resep = buat_resep(self.lain)
        res = self.client.post(reverse("modul5-recipe-edit", args=[resep.pk]), DATA_VALID)
        self.assertEqual(res.status_code, 404)

    def test_edit_tidak_valid_tidak_menyimpan(self):
        resep = buat_resep(self.user)
        data = {**DATA_VALID, "nama": ""}
        res = self.client.post(reverse("modul5-recipe-edit", args=[resep.pk]), data)
        self.assertEqual(res.status_code, 200)
        resep.refresh_from_db()
        self.assertEqual(resep.nama, "Nasi goreng telur")

    # ---------- Delete ----------
    def test_hapus_resep(self):
        resep = buat_resep(self.user)
        res = self.client.post(reverse("modul5-recipe-delete", args=[resep.pk]))
        self.assertEqual(res.status_code, 302)
        self.assertFalse(MyRecipe.objects.filter(pk=resep.pk).exists())

    def test_hapus_lewat_get_ditolak(self):
        resep = buat_resep(self.user)
        res = self.client.get(reverse("modul5-recipe-delete", args=[resep.pk]))
        self.assertEqual(res.status_code, 405)
        self.assertTrue(MyRecipe.objects.filter(pk=resep.pk).exists())

    def test_hapus_resep_user_lain_404(self):
        resep = buat_resep(self.lain)
        res = self.client.post(reverse("modul5-recipe-delete", args=[resep.pk]))
        self.assertEqual(res.status_code, 404)
        self.assertTrue(MyRecipe.objects.filter(pk=resep.pk).exists())


class MyRecipeLoginTest(TestCase):
    def test_semua_url_redirect_ke_login_kalau_belum_login(self):
        user = User.objects.create_user(username="aiko", password="rahasia123")
        resep = buat_resep(user)
        urls = [
            reverse("modul5-recipe-create"),
            reverse("modul5-recipe-detail", args=[resep.pk]),
            reverse("modul5-recipe-edit", args=[resep.pk]),
        ]
        for url in urls:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 302, url)
            self.assertIn("login", res.url, url)