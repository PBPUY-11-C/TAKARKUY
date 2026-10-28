from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

GUEST_PAGES = ["landing", "login", "signup"]
USER_PAGES = ["modul1", "modul2", "modul3", "modul4", "modul5", "food-preferences", "password-change"]


class SharedBaseTemplateTests(TestCase):
    fixtures = ["catalog_seed"]

    def setUp(self):
        self.user = get_user_model().objects.create_user("desain", password="Desain-Rapi-2026")

    def pages(self):
        for name in GUEST_PAGES:
            yield name, self.client.get(reverse(name))
        self.client.force_login(self.user)
        for name in USER_PAGES:
            yield name, self.client.get(reverse(name))

    def test_every_page_extends_one_shared_base(self):
        for name, response in self.pages():
            with self.subTest(page=name):
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "base.html")
                html = response.content.decode()
                self.assertEqual(html.count("<!DOCTYPE html>"), 1)
                self.assertEqual(html.count("takarkuy/base.css"), 1)
                self.assertEqual(html.count('name="viewport"'), 1)

    def test_every_page_offers_theme_switch_and_applies_theme_before_paint(self):
        for name, response in self.pages():
            with self.subTest(page=name):
                html = response.content.decode()
                self.assertIn("data-theme-toggle", html)
                self.assertIn('role="switch"', html)
                self.assertIn('aria-checked="false"', html)
                self.assertIn("takarkuy/theme.css", html)
                self.assertLess(html.index("takarkuy-theme"), html.index("takarkuy/base.css"))


class ThemeTokenTests(TestCase):
    def test_dark_theme_redefines_shared_tokens(self):
        css = open(finders.find("takarkuy/theme.css"), encoding="utf-8").read()
        self.assertIn(':root[data-theme="dark"]', css)
        self.assertIn("color-scheme: dark", css)
        for token in ("--canvas", "--surface", "--ink", "--muted", "--line"):
            with self.subTest(token=token):
                self.assertIn(token, css)
