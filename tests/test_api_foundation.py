import json
import re

from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase, TestCase
from django.urls import get_resolver

from scripts.cek_api import ENDPOINTS, cek_semua

LOCAL_ORIGIN = "http://localhost:5055"


class ApiErrorFormatTests(TestCase):
    """Semua error API memakai satu bentuk: {"error": pesan, "code": kode} (+ "fields")."""

    def test_unauthenticated_request(self):
        response = self.client.get("/api/planner/plans/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "not_authenticated")
        self.assertIsInstance(response.json()["error"], str)

    def test_wrong_method(self):
        self.client.force_login(get_user_model().objects.create_user("penakar"))
        response = self.client.get("/api/auth/password/")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["code"], "method_not_allowed")

    def test_non_json_body(self):
        self.client.force_login(get_user_model().objects.create_user("penakar"))
        response = self.client.post("/api/planner/plans/", {"budget": "1"})
        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.json()["code"], "unsupported_media_type")

    def test_malformed_json(self):
        self.client.force_login(get_user_model().objects.create_user("penakar"))
        response = self.client.post(
            "/api/planner/plans/", data="{rusak", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "parse_error")


class ApiDocsTests(TestCase):
    def test_schema_lists_every_module(self):
        response = self.client.get("/api/schema/?format=json")
        self.assertEqual(response.status_code, 200)
        paths = json.loads(response.content)["paths"]
        for prefix in ("/api/planner/", "/api/auth/", "/api/pantry/", "/api/recipes/", "/api/dashboard/"):
            self.assertTrue(any(path.startswith(prefix) for path in paths), prefix)

    def test_schema_documents_every_api_route(self):
        def api_routes(patterns, prefix=""):
            for pattern in patterns:
                route = prefix + str(pattern.pattern)
                if hasattr(pattern, "url_patterns"):
                    yield from api_routes(pattern.url_patterns, route)
                elif route.startswith("api/") and not route.startswith(("api/schema", "api/docs", "api/redoc")):
                    # drf-spectacular menamai parameter pk sebagai id di dokumentasi.
                    path = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", route).replace("{pk}", "{id}")
                    yield "/" + path

        documented = set(json.loads(self.client.get("/api/schema/?format=json").content)["paths"])
        missing = sorted(set(api_routes(get_resolver().url_patterns)) - documented)
        self.assertEqual(missing, [])

    def test_schema_describes_token_header_authentication(self):
        schema = json.loads(self.client.get("/api/schema/?format=json").content)
        schemes = schema["components"]["securitySchemes"]
        self.assertIn({"type": "apiKey", "in": "header", "name": "Authorization", "description": "Token <token>"}, schemes.values())

    def test_swagger_and_redoc_pages(self):
        for url in ("/api/docs/", "/api/redoc/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertIn("text/html", response["Content-Type"])


class ApiCorsTests(TestCase):
    """Flutter di Chrome (localhost) boleh memanggil API; situs lain tidak."""

    def preflight(self, origin, path="/api/planner/plans/"):
        return self.client.options(
            path,
            HTTP_ORIGIN=origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type",
        )

    def test_localhost_is_allowed_with_cookies(self):
        response = self.preflight(LOCAL_ORIGIN)
        self.assertEqual(response["Access-Control-Allow-Origin"], LOCAL_ORIGIN)
        self.assertEqual(response["Access-Control-Allow-Credentials"], "true")

    def test_other_sites_are_not_allowed(self):
        response = self.preflight("https://situs-lain.example")
        self.assertNotIn("Access-Control-Allow-Origin", response)

    def test_web_pages_are_not_opened_to_cors(self):
        response = self.preflight(LOCAL_ORIGIN, path="/planner/")
        self.assertNotIn("Access-Control-Allow-Origin", response)


class CekApiScriptTests(LiveServerTestCase):
    """Skrip cek_api login lalu memanggil satu endpoint GET dari tiap modul."""

    def test_every_module_endpoint_responds(self):
        get_user_model().objects.create_user("penguji", password="Takar#Uji2026x")
        results = cek_semua(self.live_server_url, "penguji", "Takar#Uji2026x")

        self.assertEqual([name for name, _, _ in results], ["Login", *ENDPOINTS, "Logout"])
        self.assertEqual([status for _, _, status in results], [200, 200, 200, 200, 200, 200, 204])

    def test_wrong_password_stops_after_login(self):
        get_user_model().objects.create_user("penguji", password="Takar#Uji2026x")
        results = cek_semua(self.live_server_url, "penguji", "salah")

        self.assertEqual(results, [("Login", "/api/auth/login/", 401)])
