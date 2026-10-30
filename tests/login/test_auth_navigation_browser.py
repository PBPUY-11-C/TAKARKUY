"""Opt-in browser checks for the home link beside the authentication theme switch."""

import os
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse


@skipUnless(os.getenv("TAKARKUY_BROWSER_VERIFY") == "1", "Opt-in local Chrome verification")
class AuthNavigationBrowserTests(StaticLiveServerTestCase):
    def test_home_link_sits_beside_theme_switch_and_works_with_keyboard(self):
        from playwright.sync_api import expect, sync_playwright

        artifacts = Path(settings.BASE_DIR) / ".verification" / "modul3-tdd" / "auth-navigation"
        artifacts.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as automation:
            browser = automation.chromium.launch(channel="chrome", headless=True)
            for theme in ("light", "dark"):
                context = browser.new_context()
                context.add_init_script(f"localStorage.setItem('takarkuy-theme', '{theme}')")
                context.route("https://**/*", lambda route: route.abort())
                page = context.new_page()
                card_sizes = {}
                for route in ("login", "signup"):
                    for width in (320, 1280):
                        page.set_viewport_size({"width": width, "height": 900})
                        response = page.goto(self.live_server_url + reverse(route))
                        self.assertEqual(response.status, 200)
                        submit = page.locator(".auth-card form button[type=submit]")
                        expect(submit).to_have_css("background-color",
                            "rgb(212, 244, 90)" if theme == "dark" else "rgb(15, 61, 46)")
                        expect(submit).to_have_css("color",
                            "rgb(11, 53, 34)" if theme == "dark" else "rgb(255, 255, 255)")
                        card = page.locator(".auth-card")
                        metrics = card.evaluate("""element => {
                            const style = getComputedStyle(element);
                            return {width: element.getBoundingClientRect().width,
                                padding: style.padding, radius: style.borderRadius};
                        }""")
                        if route == "login":
                            card_sizes[width] = metrics
                        else:
                            self.assertEqual(metrics, card_sizes[width],
                                "Login and signup must share card width, padding and corners")
                        navigation = page.get_by_role("navigation", name="Navigasi halaman akun")
                        home = navigation.get_by_role("link", name="Kembali ke beranda", exact=True)
                        switch = navigation.get_by_role("switch", name="Mode gelap")
                        expect(home).to_be_visible()
                        expect(home).to_have_attribute("href", reverse("landing"))
                        logo = home.locator(".auth-logo-dark" if theme == "dark" else ".auth-logo-light")
                        expect(logo).to_be_visible()
                        self.assertTrue(logo.evaluate("img => img.complete && img.naturalWidth > 0"))
                        expect(switch).to_be_visible()
                        home_box, switch_box = home.bounding_box(), switch.bounding_box()
                        self.assertLessEqual(home_box["x"] + home_box["width"], switch_box["x"])
                        self.assertLessEqual(abs(home_box["y"] - switch_box["y"]), 1)
                        self.assertGreaterEqual(home_box["height"], 44)
                        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width)
                        self.assertLessEqual(
                            navigation.bounding_box()["y"] + navigation.bounding_box()["height"],
                            page.locator(".auth-card").bounding_box()["y"],
                        )
                        page.screenshot(path=str(artifacts / f"{route}-{theme}-{width}.png"), full_page=True)
                        switch.focus()
                        page.keyboard.press("Shift+Tab")
                        expect(home).to_be_focused()
                        page.keyboard.press("Enter")
                        expect(page).to_have_url(self.live_server_url + reverse("landing"))
                context.close()
            browser.close()
