from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse


class AccountFlowTests(TestCase):
    def test_login_and_signup_have_explicit_link_back_to_landing(self):
        for page_name in ("login", "signup"):
            with self.subTest(page=page_name):
                response = self.client.get(reverse(page_name))
                self.assertContains(
                    response,
                    f'<a class="back-home" href="{reverse("landing")}">← Kembali ke beranda</a>',
                    html=True,
                )
        self.assertEqual(self.client.get(reverse("landing")).status_code, 200)

    def signup_data(self, **changes):
        return {
            "username": "dina",
            "full_name": "Dina Putri",
            "email": "Dina@example.com",
            "password1": "AmanSekali!827",
            "password2": "AmanSekali!827",
            **changes,
        }

    def test_landing_cta_opens_signup_and_pages_link_to_each_other(self):
        landing = self.client.get(reverse("landing"))
        self.assertContains(landing, f'href="{reverse("signup")}"')
        signup = self.client.get(reverse("signup"))
        login = self.client.get(reverse("login"))
        self.assertContains(signup, "Mulai Masak Hemat dengan <span>TAKARKUY</span>", html=False)
        self.assertContains(signup, "Jadi Penakar")
        self.assertContains(signup, "Min. 8 karakter · kapital, angka, simbol")
        self.assertNotContains(signup, '<ul class="field-errors">')
        self.assertNotContains(signup, "Pendaftaran pengguna")
        self.assertNotContains(
            signup, "Buat akun gratis untuk mengatur rencana makan dan stok dapur."
        )
        self.assertContains(signup, f'href="{reverse("login")}"')
        self.assertContains(login, "Selamat Datang Kembali")
        self.assertContains(login, f'href="{reverse("signup")}"')
        self.assertNotContains(signup, "Google")
        self.assertNotContains(login, "Google")

    def test_signup_creates_user_with_hashed_password_and_logs_in(self):
        response = self.client.post(reverse("signup"), self.signup_data())
        self.assertRedirects(response, reverse("modul5"))
        user = get_user_model().objects.get()
        self.assertEqual(user.email, "dina@example.com")
        self.assertEqual(user.first_name, "Dina")
        self.assertEqual(user.last_name, "Putri")
        self.assertTrue(user.check_password("AmanSekali!827"))
        self.assertRedirects(self.client.get(reverse("landing")), reverse("modul5"))

    def test_signup_rejects_duplicate_email_and_mismatched_password(self):
        self.client.post(reverse("signup"), self.signup_data())
        self.client.post(reverse("logout"))
        duplicate = self.client.post(reverse("signup"), self.signup_data(email="DINA@EXAMPLE.COM"))
        self.assertContains(duplicate, "Email ini sudah terdaftar")
        mismatch = self.client.post(
            reverse("signup"),
            self.signup_data(
                email="new@example.com",
                password2="BerbedaSekali!827",
            ),
        )
        self.assertContains(mismatch, "Konfirmasi kata sandi tidak cocok")
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_signup_requires_uppercase_number_and_symbol(self):
        for password in ("demodemo1.", "Demodemo!", "Demodemo1"):
            with self.subTest(password=password):
                response = self.client.post(
                    reverse("signup"),
                    self.signup_data(
                        password1=password,
                        password2=password,
                    ),
                )
                self.assertContains(response, "huruf kapital, angka, dan simbol")
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_example_password_is_accepted(self):
        response = self.client.post(
            reverse("signup"),
            self.signup_data(
                password1="Demodemo1.",
                password2="Demodemo1.",
            ),
        )
        self.assertRedirects(response, reverse("modul5"))
        self.assertTrue(get_user_model().objects.get().check_password("Demodemo1."))

    def test_login_accepts_email_case_insensitively_and_logout_requires_post(self):
        self.client.post(reverse("signup"), self.signup_data())
        self.client.post(reverse("logout"))
        login = self.client.post(
            reverse("login"),
            {
                "username": "DINA@EXAMPLE.COM",
                "password": "AmanSekali!827",
            },
        )
        self.assertRedirects(login, reverse("modul5"))
        self.assertRedirects(self.client.get(reverse("landing")), reverse("modul5"))
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("logout")), reverse("landing"))
        self.assertFalse(self.client.get(reverse("landing")).wsgi_request.user.is_authenticated)

    def test_remember_me_controls_session_expiry(self):
        self.client.post(reverse("signup"), self.signup_data())
        self.client.post(reverse("logout"))
        self.client.post(
            reverse("login"),
            {
                "username": "dina@example.com",
                "password": "AmanSekali!827",
            },
        )
        self.assertTrue(self.client.session.get_expire_at_browser_close())
        self.client.post(reverse("logout"))
        self.client.post(
            reverse("login"),
            {
                "username": "dina@example.com",
                "password": "AmanSekali!827",
                "remember_me": "1",
            },
        )
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_wrong_password_does_not_authenticate(self):
        self.client.post(reverse("signup"), self.signup_data())
        self.client.post(reverse("logout"))
        response = self.client.post(
            reverse("login"),
            {
                "username": "dina@example.com",
                "password": "wrong",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_modul5_requires_login_and_only_shows_module_header(self):
        self.assertRedirects(
            self.client.get(reverse("modul5")),
            f"{reverse('login')}?next={reverse('modul5')}",
        )
        self.client.post(reverse("signup"), self.signup_data())
        response = self.client.get(reverse("modul5"))
        self.assertContains(response, "Hai, Dina!")
        for name, label in (
            ("modul1", "Budget Meal Planner"),
            ("modul2", "Smart Pantry"),
            ("modul4", "Recipe Book"),
        ):
            self.assertContains(response, f'href="{reverse(name)}"')
            self.assertContains(response, label)
        self.assertContains(response, 'action="/logout/"')
        self.assertNotContains(response, "Masak Enak Sesuai Budget")

    def test_module_home_links_follow_login_state(self):
        for page_name in ("modul1",):
            with self.subTest(page=page_name, authenticated=False):
                response = self.client.get(reverse(page_name))
                self.assertContains(response, f'href="{reverse("landing")}"', count=2)

        self.client.post(reverse("signup"), self.signup_data())
        for page_name in ("modul1", "modul2", "modul4"):
            with self.subTest(page=page_name, authenticated=True):
                response = self.client.get(reverse(page_name))
                self.assertContains(response, f'href="{reverse("modul5")}"', count=2)

    def test_modul4_keeps_header_and_shows_recipe_book(self):
        self.client.post(reverse("signup"), self.signup_data())
        response = self.client.get(reverse("modul4"))
        self.assertContains(response, "TAKARKUY")
        self.assertContains(response, "Kembali ke beranda")
        self.assertContains(response, "Resep favorit")
        self.assertContains(response, "Riwayat masak")

    def test_signup_and_login_post_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("signup"), self.signup_data()).status_code, 403)
        self.assertEqual(
            client.post(
                reverse("login"),
                {
                    "username": "dina@example.com",
                    "password": "AmanSekali!827",
                },
            ).status_code,
            403,
        )
