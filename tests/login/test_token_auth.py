from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token


class TokenAuthenticationApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="token-penakar",
            email="token@example.com",
            password="Demo1234!",
        )

    def test_login_returns_the_users_auth_token(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": self.user.username, "password": "Demo1234!"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        token = Token.objects.get(user=self.user)
        self.assertIs(body["status"], True)
        self.assertEqual(body["username"], self.user.username)
        self.assertEqual(body["token"], token.key)

    def test_profile_accepts_the_bearer_token(self):
        token = Token.objects.create(user=self.user)

        response = self.client.get(
            "/api/auth/profile/",
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], self.user.username)

    def test_logout_deletes_the_token_and_old_token_is_rejected(self):
        token = Token.objects.create(user=self.user)
        headers = {"HTTP_AUTHORIZATION": f"Token {token.key}"}

        response = self.client.post("/api/auth/logout/", **headers)

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Token.objects.filter(user=self.user).exists())
        rejected = self.client.get("/api/auth/profile/", **headers)
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(rejected.json()["code"], "not_authenticated")

    def test_wrong_password_does_not_create_a_token(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": self.user.username, "password": "wrong"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(Token.objects.filter(user=self.user).exists())
