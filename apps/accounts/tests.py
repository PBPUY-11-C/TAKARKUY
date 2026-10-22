from django.test import Client, TestCase
from django.urls import reverse


class AccountFlowTests(TestCase):
    def signup_data(self, **changes):
        return {
            "username": "dina",
            "full_name": "Dina Putri",
            "email": "Dina@example.com",
            "password1": "AmanSekali!827",
            "password2": "AmanSekali!827",
            **changes,
        }

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


class LaunchPageTests(TestCase):
    def test_launch_page_links_planner_and_auth_pages_are_blank(self):
        landing = self.client.get(reverse("landing"))
        self.assertContains(landing, f'href="{reverse("modul1")}"')
        self.assertContains(landing, f'href="{reverse("login")}"')
        self.assertContains(landing, f'href="{reverse("signup")}"')
        self.assertEqual(reverse("modul1"), "/planner/")
        for name in ("login", "signup"):
            self.assertContains(self.client.get(reverse(name)), "<body></body>", html=False)
