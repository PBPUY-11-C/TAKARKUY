"""Opt-in Chrome checks against an isolated Django test database.

PowerShell: $env:TAKARKUY_BROWSER_VERIFY='1'
python manage.py test apps.accounts.test_browser --noinput
Requires the optional playwright package and an installed Chrome browser.
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.db import connections

from apps.budget_planner.models import BudgetPlan
from apps.catalog.models import Ingredient

from .models import FoodPreference, UserProfile


@skipUnless(os.getenv("TAKARKUY_BROWSER_VERIFY") == "1", "Opt-in local Chrome verification")
class AccountBrowserTests(StaticLiveServerTestCase):
    fixtures = ["catalog_seed"]

    def test_guest_account_preferences_and_responsive_pages(self):
        from playwright.sync_api import expect, sync_playwright

        artifacts = Path(settings.BASE_DIR) / ".verification" / "modul3"
        artifacts.mkdir(parents=True, exist_ok=True)
        report = []
        errors = []
        with ThreadPoolExecutor(max_workers=1) as executor:
            automation = self.enterContext(sync_playwright())

            def database(callback):
                def run():
                    try:
                        return callback()
                    finally:
                        connections.close_all()
                return executor.submit(run).result()

            browser = automation.chromium.launch(channel="chrome", headless=True)
            self.addCleanup(browser.close)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            # The app under test remains local and never sends real data to providers.
            page.route("https://**/*", lambda route: route.abort())

            def open_page(path):
                response = page.goto(self.live_server_url + path)
                self.assertEqual(response.status, 200)

            def capture(name, widths=(1440, 768, 390, 320)):
                for width in widths:
                    page.set_viewport_size({"width": width, "height": 1000})
                    page.screenshot(path=str(artifacts / f"{name}-{width}.png"), full_page=True)
                    metrics = page.evaluate("""() => ({
                        width: innerWidth, content: document.documentElement.scrollWidth,
                        background: getComputedStyle(document.body).backgroundColor,
                        font: getComputedStyle(document.body).fontFamily,
                        headerWidth: document.querySelector('.app-header')?.getBoundingClientRect().width ?? null,
                        primary: (() => { const button = document.querySelector('.submit, .btn-primary');
                            return button ? getComputedStyle(button).backgroundColor : null; })(),
                        duplicateIds: [...document.querySelectorAll('[id]')].map(e => e.id)
                            .filter((id, index, ids) => ids.indexOf(id) !== index)
                    })""")
                    report.append({"page": name, **metrics})
                    (artifacts / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                    self.assertLessEqual(metrics["content"], width + 1, f"Overflow: {name} at {width}: {metrics}")
                    self.assertEqual(metrics["duplicateIds"], [], f"Duplicate IDs: {name}")
                    expected_background = (
                        "rgb(246, 248, 252)" if name.startswith("planner")
                        else "rgb(255, 255, 255)" if name.endswith("placeholder")
                        else "rgb(242, 248, 244)"
                    )
                    self.assertEqual(metrics["background"], expected_background)
                    self.assertIn("Plus Jakarta Sans", metrics["font"])
                    if name in {"landing", "login", "signup", "profile"}:
                        self.assertEqual(metrics["primary"], "rgb(15, 61, 46)")
                    if name in {"profile", "planner-after-signup"}:
                        self.assertEqual(metrics["headerWidth"], width)
                page.set_viewport_size({"width": 1440, "height": 1000})

            open_page("/")
            capture("landing")
            missing = page.locator('a[href^="#"]').evaluate_all("""links => links
                .map(a => a.getAttribute('href')).filter(h => h.length > 1 && !document.getElementById(h.slice(1)))""")
            self.assertEqual(missing, [])
            page.locator("#trial-budget").fill("240000")
            page.locator("#trial-days").fill("4")
            page.locator("#trial-servings").fill("2")
            expect(page.locator("#budget-result")).to_contain_text("30.000")
            expect(page.locator("#budget-result")).to_contain_text("10.000")
            page.locator("#trial-days").fill("0")
            expect(page.locator("#budget-result")).to_contain_text("valid")
            for path in ("/planner/", "/modul1/"):
                open_page(path)
                expect(page).to_have_url(self.live_server_url + "/login/?next=" + path)
                expect(page.get_by_role("heading", name="Selamat Datang Kembali")).to_be_visible()
            open_page("/login/")
            capture("login")
            open_page("/signup/")
            capture("signup")
            expect(page.locator('[data-auth-error-popup]')).to_have_count(0)
            page.get_by_role("button", name="Jadi Penakar").click()
            popup = page.locator('[data-auth-error-popup]')
            expect(popup).to_be_visible()
            expect(popup).to_contain_text("Periksa kolom yang ditandai.")
            capture("signup-error", widths=(1440, 390, 320))
            page.get_by_role("button", name="Perbaiki", exact=True).click()
            expect(page.locator('[name="full_name"]')).to_be_focused()
            page.locator('[name="full_name"]').fill("Penguji Modul Tiga")
            page.locator('[name="username"]').fill("penguji_modul3")
            page.locator('[name="email"]').fill("browser@example.com")
            page.locator('[name="password1"]').fill("BrowserTest!827")
            page.get_by_role("button", name="Tampilkan kata sandi", exact=True).first.click()
            expect(page.locator('[name="password1"]')).to_have_attribute("type", "text")
            page.locator('[name="password2"]').fill("DifferentTest!827")
            page.get_by_role("button", name="Jadi Penakar").click()
            popup = page.locator('[data-auth-error-popup]')
            expect(popup).to_be_visible()
            expect(popup).to_contain_text("Konfirmasi kata sandi tidak cocok.")
            popup.get_by_role("button", name="Perbaiki", exact=True).click()
            expect(page.locator('[name="password2"]')).to_be_focused()
            page.locator('[name="password1"]').fill("BrowserTest!827")
            page.locator('[name="password2"]').fill("BrowserTest!827")
            page.get_by_role("button", name="Jadi Penakar").click()
            expect(page).to_have_url(self.live_server_url + "/planner/")
            user = database(lambda: get_user_model().objects.get(username="penguji_modul3"))
            self.assertTrue(database(lambda: UserProfile.objects.filter(user=user).exists()))
            self.assertTrue(database(lambda: FoodPreference.objects.filter(user=user).exists()))
            capture("planner-after-signup", widths=(1440, 390))
            page.locator('[name="budget"]').fill("1000000")
            page.locator('[name="days"]').fill("1")
            page.locator('[name="servings"]').fill("1")
            page.get_by_role("button", name="Buat Rencana Makan").click()
            expect(page.get_by_role("heading", name="Rencana makan 1 hari", exact=True)).to_be_visible()
            # Members can create, save, rename and delete their own plan.
            draft = database(lambda: BudgetPlan.objects.get(user=user, status="draft"))
            expect(page.locator("#plan-title")).to_be_visible()
            page.locator("#plan-title").fill("Rencana uji browser")
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Simpan Rencana", exact=True).click()
            expect(page.locator(".saved-plan-card")).to_contain_text("Rencana uji browser")
            saved = database(lambda: BudgetPlan.objects.get(user=user, status="saved"))
            self.assertEqual(saved.snapshot, draft.snapshot)
            page.locator("#plan-title").fill("Rencana diperbarui")
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Simpan Judul / Tanggal", exact=True).click()
            expect(page.locator(".saved-plan-card")).to_contain_text("Rencana diperbarui")
            database(saved.refresh_from_db)
            self.assertEqual(saved.title, "Rencana diperbarui")
            page.once("dialog", lambda dialog: dialog.accept())
            with page.expect_navigation(wait_until="networkidle"):
                page.locator("[data-delete-plan]").click()
            expect(page.locator(".saved-empty")).to_be_visible()
            self.assertFalse(database(lambda: BudgetPlan.objects.filter(pk=saved.pk).exists()))
            open_page("/profil/")
            expect(page.locator('.avatar')).to_have_text("P")
            expect(page.get_by_role("link", name="Profil dan preferensi")).to_be_visible()
            expect(page.locator("title")).to_have_count(1)
            expect(page.locator('[name="targets"]')).to_have_count(0)
            expect(page.get_by_role("heading", name="Pengaturan profil", exact=True)).to_be_visible()
            settings_nav = page.get_by_role("navigation", name="Pengaturan profil", exact=True)
            expect(settings_nav.locator('[aria-current="page"]')).to_have_text("Akun")
            capture("profile")
            page.get_by_role("navigation", name="Pengaturan profil", exact=True).get_by_role("link", name="Preferensi makanan", exact=True).click()
            expect(page).to_have_url(self.live_server_url + "/profil/preferensi/")
            expect(page.locator('select[name="avoided_ingredients"]')).to_have_count(0)
            expect(settings_nav.locator('[aria-current="page"]')).to_have_text("Preferensi makanan")
            capture("food-preferences")
            picker = page.locator('[data-ingredient-picker]')
            search = page.locator('#ingredient-search')
            search.fill('zzzz-not-a-food')
            expect(picker.locator('.ingredient-empty')).to_be_visible()
            search.fill('')
            ingredients = picker.locator('input[type="checkbox"]')
            for index in range(10):
                ingredients.nth(index).check()
            expect(page.locator('#ingredient-count')).to_have_text('10/10 dipilih')
            expect(ingredients.nth(10)).to_be_disabled()
            ingredients.nth(0).uncheck()
            expect(ingredients.nth(10)).to_be_enabled()
            while picker.locator('input:checked').count():
                picker.locator('input:checked').first.uncheck()
            expect(page.locator('#ingredient-count')).to_have_text('0/10 dipilih')
            expect(page.locator('[name="halal_only"]')).to_have_count(0)
            page.locator('[name="targets"][value="tinggi_protein"]').check()
            page.get_by_role("button", name="Simpan preferensi", exact=True).click()
            expect(page.get_by_text("Seimbang tidak dapat digabung dengan target lain.")).to_be_visible()
            page.locator('[name="targets"][value="tinggi_protein"]').uncheck()
            page.locator('[name="servings"]').fill("3")
            page.locator('[name="allergens"][value="telur"]').check()
            ingredient = database(lambda: Ingredient.objects.order_by("pk").first())
            page.locator('[name="avoided_ingredients"][value="' + ingredient.pk + '"]').check()
            page.get_by_role("button", name="Simpan preferensi", exact=True).click()
            expect(page.get_by_text("Perubahan berhasil disimpan.")).to_be_visible()
            preference = database(lambda: FoodPreference.objects.get(user=user))
            expect(page.locator('[name="avoided_ingredients"][value="' + ingredient.pk + '"]')).to_be_checked()
            expect(page.locator("#ingredient-count")).to_have_text("1/10 dipilih")
            self.assertTrue(preference.halal_only)
            self.assertEqual(preference.servings, 3)
            self.assertEqual(preference.allergens, ["telur"])
            self.assertTrue(database(lambda: preference.avoided_ingredients.filter(pk=ingredient.pk).exists()))
            page.get_by_role("navigation", name="Pengaturan profil", exact=True).get_by_role("link", name="Akun", exact=True).click()
            expect(page).to_have_url(self.live_server_url + "/profil/")
            page.locator('[name="email"]').fill("browser-new@example.com")
            page.get_by_role("button", name="Simpan informasi akun").click()
            expect(page.get_by_text("Masukkan kata sandi saat ini untuk mengganti email.")).to_be_visible()
            page.locator('[name="current_password"]').fill("BrowserTest!827")
            page.locator('[name="full_name"]').fill("Penguji Baru")
            page.get_by_role("button", name="Simpan informasi akun").click()
            database(user.refresh_from_db)
            self.assertEqual(user.email, "browser-new@example.com")
            self.assertEqual(user.get_full_name(), "Penguji Baru")
            expect(page.locator('[name="old_password"]')).to_have_count(0)
            page.get_by_role("navigation", name="Pengaturan profil", exact=True).get_by_role("link", name="Keamanan akun", exact=True).click()
            expect(page).to_have_url(self.live_server_url + "/profil/ganti-kata-sandi/")
            expect(settings_nav.locator('[aria-current="page"]')).to_have_text("Keamanan akun")
            capture("password-change", widths=(1440, 390, 320))
            page.locator('[name="old_password"]').fill("BrowserTest!827")
            page.locator('[name="new_password1"]').fill("BrowserChanged!938")
            page.locator('[name="new_password2"]').fill("BrowserChanged!938")
            page.get_by_role("button", name="Ganti kata sandi", exact=True).click()
            expect(page).to_have_url(self.live_server_url + "/profil/")
            database(user.refresh_from_db)
            self.assertTrue(user.check_password("BrowserChanged!938"))
            open_page("/planner/?new=1")
            expect(page.locator('[name="servings"]')).to_have_value("3")
            expect(page.get_by_text("Preferensi halal:", exact=False)).to_have_count(0)
            capture("planner", widths=(1440, 390))
            for path, name in (("/modul2/", "pantry"), ("/modul4/", "recipe-book"), ("/modul5/", "dashboard")):
                open_page(path)
                expect(page.locator('.app-header')).to_be_visible()
                capture(name, widths=(1440, 390))
            open_page("/profil/")
            logout = page.locator('form[action="/logout/"] button')
            expect(logout).to_be_visible()
            logout.click()
            expect(page).to_have_url(self.live_server_url + "/")
            open_page("/planner/")
            expect(page).to_have_url(self.live_server_url + "/login/?next=/planner/")
            open_page("/login/")
            page.locator('[name="username"]').fill("browser-new@example.com")
            page.locator('[name="password"]').fill("BrowserChanged!938")
            page.locator('[name="password"]').fill("IncorrectPassword!123")
            page.get_by_role("button", name="Masuk ke TAKARKUY").click()
            popup = page.locator('[data-auth-error-popup]')
            expect(popup).to_be_visible()
            expect(popup).to_contain_text("Email/username atau kata sandi salah.")
            capture("login-error", widths=(1440, 390, 320))
            page.keyboard.press("Escape")
            expect(popup).not_to_be_visible()
            expect(page.locator('[name="username"]')).to_be_focused()
            page.locator('[name="password"]').fill("BrowserChanged!938")
            page.get_by_role("button", name="Masuk ke TAKARKUY").click()
            expect(page).to_have_url(self.live_server_url + "/planner/")
            session = next(c for c in context.cookies() if c["name"] == settings.SESSION_COOKIE_NAME)
            self.assertEqual(session["expires"], -1)
            # Re-authenticating in the same browser must also honor Remember me.
            open_page("/login/")
            page.locator('[name="username"]').fill("browser-new@example.com")
            page.locator('[name="password"]').fill("BrowserChanged!938")
            page.locator('[name="remember_me"]').check()
            page.get_by_role("button", name="Masuk ke TAKARKUY").click()
            expect(page).to_have_url(self.live_server_url + "/planner/")
            session = next(c for c in context.cookies() if c["name"] == settings.SESSION_COOKIE_NAME)
            self.assertGreater(session["expires"], 0)
            self.assertEqual(errors, [])
            print(f"Browser screenshots and metrics: {artifacts}")
