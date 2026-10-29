"""Opt-in keyboard user journeys; run with TAKARKUY_BROWSER_VERIFY=1."""

import os
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse

from apps.login.preferences import profile_for


@skipUnless(os.getenv("TAKARKUY_BROWSER_VERIFY") == "1", "Opt-in local Chrome verification")
class AccountKeyboardBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        from playwright.sync_api import sync_playwright

        user = get_user_model().objects.create_user("keyboard-owner", first_name="Attar")
        profile_for(user)
        self.client.force_login(user)
        automation = self.enterContext(sync_playwright())
        browser = automation.chromium.launch(channel="chrome", headless=True)
        self.addCleanup(browser.close)
        self.context = browser.new_context()
        self.addCleanup(self.context.close)
        self.context.route("https://**/*", lambda route: route.abort())
        self.context.add_init_script("localStorage.setItem('takarkuy-theme', 'dark')")
        self.page = self.context.new_page()

    def open_profile(self):
        self.context.add_cookies([{
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }])
        response = self.page.goto(self.live_server_url + reverse("modul3"))
        self.assertEqual(response.status, 200)

    def test_avatar_arrows_update_selection_preview_and_tab_leaves_group(self):
        from playwright.sync_api import expect

        self.open_profile()
        page = self.page
        page.locator(".settings-nav a").last.focus()
        page.keyboard.press("Tab")
        choices = page.locator('[name="avatar"]')
        expect(choices.first).to_be_focused()
        page.keyboard.press("ArrowRight")
        expect(choices.nth(1)).to_be_checked()
        expect(choices.nth(1)).to_be_focused()
        image = page.locator("[data-avatar-preview-image]")
        expect(image).to_be_visible()
        expect(image).to_have_attribute("src", page.locator(".avatar-option").nth(1).get_attribute("data-avatar-source"))
        self.assertTrue(choices.nth(1).evaluate("e => e.matches(':focus-visible')"))
        page.keyboard.press("ArrowLeft")
        expect(choices.first).to_be_checked()
        expect(page.locator("[data-avatar-preview-initial]")).to_be_visible()
        expect(image).to_be_hidden()
        page.keyboard.press("ArrowLeft")
        expect(choices.last).to_be_checked()
        page.keyboard.press("Tab")
        expect(page.locator('[name="full_name"]')).to_be_focused()
        page.keyboard.press("Shift+Tab")
        expect(choices.last).to_be_focused()

    def check_auth_popup(self, route, field):
        from playwright.sync_api import expect

        page = self.page
        page.goto(self.live_server_url + reverse(route))
        submit = page.locator(".auth-card form button[type=submit]")
        submit.focus()
        page.keyboard.press("Enter")
        popup = page.locator("[data-auth-error-popup]")
        expect(popup).to_be_visible()
        fix = popup.get_by_role("button", name="Perbaiki", exact=True)
        close = popup.get_by_role("button", name="Tutup pemberitahuan", exact=True)
        expect(fix).to_be_focused()
        page.keyboard.press("Shift+Tab")
        expect(close).to_be_focused()
        page.keyboard.press("Shift+Tab")
        expect(fix).to_be_focused()
        page.keyboard.press("Tab")
        expect(close).to_be_focused()
        page.keyboard.press("Escape")
        expect(popup).not_to_be_visible()
        expect(page.locator(f'[name="{field}"]')).to_be_focused()
        submit.focus()
        page.keyboard.press("Enter")
        expect(popup).to_be_visible()
        expect(fix).to_be_focused()
        page.keyboard.press("Enter")
        expect(popup).not_to_be_visible()
        expect(page.locator(f'[name="{field}"]')).to_be_focused()

    def test_login_popup_tab_cycles_escape_and_enter_restore_field_focus(self):
        self.check_auth_popup("login", "username")

    def test_signup_popup_tab_cycles_escape_and_enter_restore_field_focus(self):
        self.check_auth_popup("signup", "full_name")

    def test_unsaved_popup_cycles_focus_and_keeps_edits_when_cancelled(self):
        from playwright.sync_api import expect

        self.open_profile()
        page = self.page
        name = page.locator('[name="full_name"]')
        name.fill("Nama belum disimpan")
        link = page.get_by_role("navigation", name="Pengaturan profil").get_by_role("link", name="Keamanan akun")
        link.focus()
        page.keyboard.press("Enter")
        popup = page.locator("[data-unsaved-popup]")
        stay = popup.get_by_role("button", name="Tetap di sini", exact=True)
        leave = popup.get_by_role("button", name="Tinggalkan", exact=True)
        expect(popup).to_be_visible()
        expect(stay).to_be_focused()
        page.keyboard.press("Tab")
        expect(leave).to_be_focused()
        page.keyboard.press("Tab")
        expect(stay).to_be_focused()
        page.keyboard.press("Shift+Tab")
        expect(leave).to_be_focused()
        page.keyboard.press("Escape")
        expect(popup).not_to_be_visible()
        expect(link).to_be_focused()
        expect(name).to_have_value("Nama belum disimpan")
        expect(page).to_have_url(self.live_server_url + reverse("modul3"))
        page.keyboard.press("Enter")
        expect(popup).to_be_visible()
        expect(stay).to_be_focused()
        page.keyboard.press("Enter")
        expect(popup).not_to_be_visible()
        expect(link).to_be_focused()
        expect(name).to_have_value("Nama belum disimpan")
