"""Opt-in Chromium flow: create, save, and delete a plan without reloading the page."""

import os
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse


@skipUnless(os.getenv("TAKARKUY_BROWSER_VERIFY") == "1", "Opt-in local Chromium verification")
class PlannerBrowserTests(StaticLiveServerTestCase):
    fixtures = ["catalog_seed"]

    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("perencana"))
        self.session = self.client.cookies["sessionid"].value

    def test_plan_crud_runs_without_page_reload(self):
        from playwright.sync_api import expect, sync_playwright

        with sync_playwright() as automation:
            browser = automation.chromium.launch()
            context = browser.new_context()
            context.route("https://**/*", lambda route: route.abort())
            context.add_cookies(
                [{"name": "sessionid", "value": self.session, "url": self.live_server_url}]
            )
            page = context.new_page()
            page.on("dialog", lambda dialog: dialog.accept())
            page.goto(self.live_server_url + reverse("modul1"))
            page.evaluate("window.__samePage = true")
            stayed = "() => window.__samePage === true"

            page.click(".planner-form button[type=submit]")
            expect(page.locator("[data-save-plan]")).to_be_visible()
            self.assertIn("?plan=", page.url)
            self.assertTrue(page.evaluate(stayed), "Buat rencana me-reload halaman")

            page.fill("#plan-title", "Rencana uji")
            page.click("[data-save-plan] button[type=submit]")
            expect(page.locator("[data-save-plan] .status")).to_contain_text("Tersimpan")
            expect(page.locator("[data-saved-count]").first).to_have_text("1")
            self.assertTrue(page.evaluate(stayed), "Simpan me-reload halaman")

            page.click("[data-open-dialog='rencana-saya']")
            rows = page.locator(".saved-list [data-delete-plan]")
            expect(rows).to_have_count(1)
            page.route(
                "**/delete/",
                lambda route: route.fulfill(
                    status=500, content_type="application/json", body='{"error": "Server gagal."}'
                ),
            )
            page.click(".saved-list [data-delete-plan]")
            expect(rows).to_have_count(1)
            expect(page.locator("#plan-feedback")).to_contain_text("Server gagal.")
            page.unroute("**/delete/")

            page.click(".saved-list [data-delete-plan]")
            expect(rows).to_have_count(0)
            expect(page.locator("[data-saved-count]").first).to_have_text("0")
            expect(page.locator(".empty-state")).to_be_visible()
            self.assertTrue(page.evaluate(stayed), "Hapus me-reload halaman")
            browser.close()
