"""Opt-in regression checks for the three profile settings pages.

Run with TAKARKUY_BROWSER_VERIFY=1 and an installed Chrome browser.
"""

import os
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse

from apps.catalog.models import Ingredient
from apps.login.preferences import preferences_for, profile_for


CONTRAST_AUDIT = (Path(__file__).parents[1] / "contrast_audit.js").read_text(encoding="utf-8")


@skipUnless(os.getenv("TAKARKUY_BROWSER_VERIFY") == "1", "Opt-in local Chrome verification")
class SettingsThemeBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        user = get_user_model().objects.create_user("theme-owner", first_name="Attar")
        profile_for(user)
        preferences = preferences_for(user)
        preferences.allergens = ["telur"]
        preferences.save()
        ingredient = Ingredient.objects.create(
            ingredient_code="THEME-TEST", name="Bahan uji", category="sayur", base_unit="g"
        )
        preferences.avoided_ingredients.add(ingredient)
        self.client.force_login(user)

    def test_settings_text_remains_readable_in_dark_theme(self):
        from playwright.sync_api import expect, sync_playwright

        artifacts = Path(settings.BASE_DIR) / ".verification" / "modul3-tdd" / "settings-dark"
        artifacts.mkdir(parents=True, exist_ok=True)
        problems = []
        errors = []
        with sync_playwright() as automation:
            browser = automation.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            context.add_init_script("localStorage.setItem('takarkuy-theme', 'dark')")
            context.route("https://**/*", lambda route: route.abort())
            context.add_cookies([{
                "name": settings.SESSION_COOKIE_NAME,
                "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
                "url": self.live_server_url,
            }])
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            for route in ("modul3", "food-preferences", "password-change"):
                response = page.goto(self.live_server_url + reverse(route))
                self.assertEqual(response.status, 200)
                expect(page.locator("html")).to_have_attribute("data-theme", "dark")
                expect(page.get_by_role("heading", name="Pengaturan profil", exact=True)).to_be_visible()
                problems.extend({"page": route, **row} for row in page.evaluate(CONTRAST_AUDIT))
                if route == "food-preferences":
                    # Audit selected allergy/ingredient controls, not just empty defaults.
                    expect(page.locator('[name="allergens"][value="telur"]')).to_be_checked()
                    expect(page.locator("[data-selected-ingredients]")).to_contain_text("Bahan uji")
                page.screenshot(path=str(artifacts / f"{route}.png"), full_page=True)
            context.close()
            browser.close()
        self.assertEqual(errors, [], "Browser JavaScript errors")
        self.assertEqual(problems, [], "Settings text must meet WCAG AA contrast in dark mode")
