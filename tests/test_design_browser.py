"""Opt-in Chromium checks: no horizontal overflow and a working dark theme on every page."""

import os
from pathlib import Path
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse

from tests.test_design_system import GUEST_PAGES, USER_PAGES

WIDTHS = (360, 768, 1280)
CONTRAST_AUDIT = (Path(__file__).parent / "contrast_audit.js").read_text(encoding="utf-8")


@skipUnless(os.getenv("TAKARKUY_BROWSER_VERIFY") == "1", "Opt-in local Chromium verification")
class DesignBrowserTests(StaticLiveServerTestCase):
    fixtures = ["catalog_seed"]

    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("layar"))
        self.session = self.client.cookies["sessionid"].value
        self.paths = [(reverse(name), False) for name in GUEST_PAGES] + [
            (reverse(name), True) for name in USER_PAGES
        ]

    def open(self, browser, width, theme, signed_in):
        context = browser.new_context(viewport={"width": width, "height": 900})
        context.add_init_script(f"localStorage.setItem('takarkuy-theme', '{theme}')")
        context.route("https://**/*", lambda route: route.abort())
        if signed_in:
            context.add_cookies(
                [{"name": "sessionid", "value": self.session, "url": self.live_server_url}]
            )
        return context

    def test_pages_fit_small_screens_in_both_themes(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as automation:
            browser = automation.chromium.launch()
            problems = []
            for theme in ("light", "dark"):
                for width in WIDTHS:
                    for signed_in in (False, True):
                        context = self.open(browser, width, theme, signed_in)
                        page = context.new_page()
                        for path, needs_login in self.paths:
                            if needs_login != signed_in:
                                continue
                            page.goto(self.live_server_url + path)
                            state = page.evaluate(
                                """() => ({
                                    theme: document.documentElement.dataset.theme,
                                    overflow: document.documentElement.scrollWidth - innerWidth,
                                    body: getComputedStyle(document.body).backgroundColor,
                                })"""
                            )
                            channels = [int(v) for v in state["body"][4:-1].split(",")[:3]]
                            dark = sum(channels) / 3 < 80
                            if theme == "dark" and width == 1280:
                                for row in page.evaluate(CONTRAST_AUDIT):
                                    problems.append(
                                        f"{path} kontras {row['ratio']} pada {row['el']} '{row['text']}'"
                                    )
                            if state["overflow"] > 0:
                                problems.append(f"{path} {width}px melebar {state['overflow']}px")
                            if state["theme"] != theme or dark != (theme == "dark"):
                                problems.append(f"{path} {width}px tema {theme} tidak diterapkan")
                        context.close()
            browser.close()
        self.assertEqual(problems, [])

    def test_theme_switch_persists_after_reload(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as automation:
            browser = automation.chromium.launch()
            context = browser.new_context(color_scheme="light")
            context.add_cookies(
                [{"name": "sessionid", "value": self.session, "url": self.live_server_url}]
            )
            page = context.new_page()
            page.goto(self.live_server_url + reverse("modul5"))
            self.assertEqual(page.evaluate("document.documentElement.dataset.theme"), "light")
            page.click("[data-theme-toggle]")
            self.assertEqual(page.evaluate("document.documentElement.dataset.theme"), "dark")
            page.reload()
            self.assertEqual(page.evaluate("document.documentElement.dataset.theme"), "dark")
            self.assertEqual(page.get_attribute("[data-theme-toggle]", "aria-checked"), "true")
            page.evaluate("TakarKuy.toast('Rencana tersimpan.'); TakarKuy.toast('Gagal.', 'error')")
            self.assertEqual(page.evaluate(CONTRAST_AUDIT), [])
            browser.close()
