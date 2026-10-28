from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client, TestCase
from django.urls import reverse


class ErrorPageTests(TestCase):
    def test_unknown_url_uses_branded_404(self):
        response = self.client.get("/halaman-yang-tidak-ada/")
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")
        self.assertContains(response, "Halaman tidak ditemukan", status_code=404)
        self.assertContains(response, f'href="{reverse("landing")}"', status_code=404)

    def test_404_links_signed_in_users_to_their_pages(self):
        self.client.force_login(get_user_model().objects.create_user("tersesat"))
        response = self.client.get("/halaman-yang-tidak-ada/")
        self.assertContains(response, f'href="{reverse("modul5")}"', status_code=404)
        self.assertContains(response, f'href="{reverse("modul1")}"', status_code=404)

    def test_expired_form_uses_csrf_page(self):
        response = Client(enforce_csrf_checks=True).post(reverse("login"), {})
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "403_csrf.html")
        self.assertContains(response, "Sesi kedaluwarsa", status_code=403)

    def test_403_and_500_render_without_request_context(self):
        for template, heading in (("403.html", "Akses ditolak"), ("500.html", "server kami")):
            with self.subTest(template=template):
                self.assertIn(heading, render_to_string(template))
