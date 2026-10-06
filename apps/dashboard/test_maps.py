import json
import subprocess
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .maps import (
    MapLimited,
    MapUnavailable,
    _http,
    curated,
    geocode_region,
    osm_places,
    read_places,
)
from .models import MapLookupCache, MapProviderGate, MapQuota


class MapTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("petaku")
        self.client.force_login(self.user)

    def post(self, **changes):
        return self.client.post(
            reverse("modul5-places"),
            json.dumps({"region": "Garut", **changes}),
            content_type="application/json",
        )

    @patch("apps.dashboard.maps.osm_places")
    def test_curated_default_never_calls_provider_and_sources_are_present(self, provider):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["places"]), 3)
        provider.assert_not_called()
        for place in read_places()["places"]:
            self.assertTrue(place["source_url"].startswith("https://"))
        bank = curated("Depok", "waste_bank")["places"][0]
        self.assertIsNone(bank["lat"])
        self.assertEqual(curated("Garut", "waste_bank")["places"], [])

    def test_missing_area_is_honest_not_demo_places(self):
        response = self.post(region="Jayapura")
        self.assertEqual(response.json()["places"], [])
        self.assertIn("belum tersedia", response.json()["message"])

    def test_coordinates_personal_addresses_and_invalid_types_not_accepted(self):
        for data in (
            {"lat": -6.3},
            {"lng": 106.8},
            {"region": "person@example.com"},
            {"region": "Jl Rumah 123"},
            {"region": {}},
            {"region": " "},
            {"kind": []},
            {"online": "true"},
        ):
            with self.subTest(data=data):
                self.assertEqual(self.post(**data).status_code, 400)
        self.assertEqual(MapLookupCache.objects.count(), 0)

    def test_login_method_and_csrf(self):
        self.assertEqual(
            Client()
            .post(reverse("modul5-places"), "{}", content_type="application/json")
            .status_code,
            403,
        )
        self.assertEqual(self.client.get(reverse("modul5-places")).status_code, 405)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.user)
        self.assertEqual(
            csrf.post(reverse("modul5-places"), "{}", content_type="application/json").status_code,
            403,
        )

    @override_settings(MAP_LOOKUP_ENABLED=False)
    @patch("apps.dashboard.maps.osm_places")
    def test_online_is_operator_opt_in(self, provider):
        result = self.post(online=True).json()
        self.assertEqual(result["source"], "curated")
        self.assertIn("belum diaktifkan", result["message"])
        provider.assert_not_called()
        self.assertFalse(MapQuota.objects.exists())

    @override_settings(MAP_LOOKUP_ENABLED=True)
    @patch(
        "apps.dashboard.maps.osm_places",
        return_value={"places": [], "source": "osm", "message": "Data belum tersedia"},
    )
    def test_empty_online_results_fall_back_to_curated(self, provider):
        self.assertEqual(self.post(online=True).json()["source"], "curated")

    @override_settings(MAP_LOOKUP_ENABLED=True)
    @patch("apps.dashboard.maps.osm_places")
    def test_shared_cache_serves_other_accounts_without_second_provider_call(self, provider):
        provider.return_value = {"places": [{"name": "Pasar OSM"}], "source": "osm", "message": ""}
        self.assertEqual(self.post(online=True).status_code, 200)
        self.client.force_login(get_user_model().objects.create_user("petamu"))
        second = self.post(region=" GARUT ", online=True).json()
        self.assertTrue(second["cached"])
        self.assertEqual(provider.call_count, 1)
        cache = MapLookupCache.objects.get()
        self.assertEqual(len(cache.key), 64)
        self.assertNotIn("user", cache.payload)
        self.assertNotIn("gps", cache.payload)

    @override_settings(MAP_LOOKUP_ENABLED=True)
    @patch("apps.dashboard.maps.osm_places", side_effect=MapUnavailable("timeout"))
    def test_provider_failure_returns_curated_not_500(self, provider):
        response = self.post(online=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "curated")
        self.assertFalse(MapLookupCache.objects.exists())

    @override_settings(MAP_LOOKUP_ENABLED=True)
    @patch("apps.dashboard.maps.osm_places", side_effect=MapLimited(2))
    def test_provider_busy_returns_curated_without_retry_loop(self, provider):
        response = self.post(online=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "curated")
        self.assertEqual(response.json()["retry_after"], 2)
        self.assertEqual(len(response.json()["places"]), 3)
        self.assertIn("sedang sibuk", response.json()["message"])
        self.assertFalse(MapLookupCache.objects.exists())
        self.assertEqual(provider.call_count, 1)

    @override_settings(MAP_LOOKUP_ENABLED=True)
    @patch("apps.dashboard.maps.osm_places")
    def test_account_quota_survives_another_client(self, provider):
        provider.return_value = {"places": [{"name": "Pasar OSM"}], "source": "osm", "message": ""}
        for _ in range(10):
            self.assertEqual(self.post(online=True).status_code, 200)
        client = Client()
        client.force_login(self.user)
        response = client.post(
            reverse("modul5-places"),
            json.dumps({"region": "Garut", "online": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response["Retry-After"]), 0)
        self.assertEqual(provider.call_count, 1)
        MapQuota.objects.update(window_started_at=timezone.now() - timedelta(minutes=11))
        self.assertEqual(self.post(online=True).status_code, 200)

    @override_settings(MAP_LOOKUP_ENABLED=True)
    @patch("apps.dashboard.maps.osm_places")
    def test_offline_lookups_do_not_create_or_spend_quota(self, provider):
        for _ in range(12):
            self.assertEqual(self.post().status_code, 200)
        self.assertFalse(MapQuota.objects.exists())
        MapQuota.objects.create(user=self.user, window_started_at=timezone.now(), attempts=10)
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(MapQuota.objects.get().attempts, 10)
        provider.assert_not_called()

    @patch("apps.dashboard.maps._http")
    def test_osm_cleans_types_coordinates_and_does_not_call_every_recycling_point_bank(self, http):
        http.side_effect = [
            [{"lat": "-7.2", "lon": "107.9", "addresstype": "city"}],
            {
                "elements": [
                    {
                        "type": "node",
                        "id": 1,
                        "lat": -7.2,
                        "lon": 107.9,
                        "tags": {"name": "Pasar", "amenity": "marketplace"},
                    },
                    {
                        "type": "way",
                        "id": 2,
                        "center": {"lat": -7.21, "lon": 107.91},
                        "tags": {"name": "Bank Sampah Bersih"},
                    },
                    {
                        "type": "node",
                        "id": 3,
                        "lat": -7.2,
                        "lon": 107.9,
                        "tags": {"name": "Tempat sampah", "amenity": "recycling"},
                    },
                    {
                        "type": "node",
                        "id": 4,
                        "lat": "nan",
                        "lon": 107.9,
                        "tags": {"name": "Invalid", "amenity": "marketplace"},
                    },
                    {
                        "type": "node",
                        "id": 5,
                        "lat": -7.2,
                        "lon": 107.9,
                        "tags": {"name": {}, "amenity": "marketplace"},
                    },
                ]
            },
        ]
        result = osm_places("Garut", "all")
        self.assertEqual([p["kind"] for p in result["places"]], ["market", "waste_bank"])
        self.assertEqual(http.call_count, 2)
        self.assertIn("out+center+30", http.call_args.args[2])

    @patch("apps.dashboard.maps._http")
    def test_geocoder_cache_shared_when_filter_changes(self, http):
        http.side_effect = [
            [{"lat": "-7.2", "lon": "107.9", "addresstype": "city"}],
            {"elements": []},
            {"elements": []},
        ]
        osm_places("garut", "market")
        osm_places("garut", "waste_bank")
        self.assertEqual(
            [call.args[0] for call in http.call_args_list],
            ["nominatim", "overpass", "overpass"],
        )

    @patch("apps.dashboard.maps._http")
    def test_geocoder_rejects_non_administrative_result(self, http):
        http.return_value = [{"lat": "-7.2", "lon": "107.9", "addresstype": "road"}]
        with self.assertRaises(MapUnavailable):
            geocode_region("garut")
        self.assertFalse(MapLookupCache.objects.exists())

    @override_settings(MAP_USER_AGENT="TAKARKUY/1.0 (+https://github.com/PBPUY-11-C/TAKARKUY)")
    @patch("apps.dashboard.maps.subprocess.run")
    def test_shared_provider_gate_enforces_cooldown_even_after_timeout(self, run):
        run.side_effect = subprocess.TimeoutExpired("maps", 8)
        with self.assertRaises(MapUnavailable):
            _http("nominatim", "https://nominatim.openstreetmap.org/search?q=garut")
        gate = MapProviderGate.objects.get()
        self.assertIsNone(gate.lease)
        with self.assertRaises(MapLimited):
            _http("nominatim", "https://nominatim.openstreetmap.org/search?q=depok")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.kwargs["timeout"], 8)

    @override_settings(MAP_USER_AGENT="")
    @patch("apps.dashboard.maps.subprocess.run")
    def test_no_identifying_agent_means_no_outbound_request(self, run):
        with self.assertRaises(MapUnavailable):
            _http("nominatim", "https://nominatim.openstreetmap.org/search")
        run.assert_not_called()

    @override_settings(MAP_USER_AGENT="TAKARKUY/1.0 (+https://github.com/PBPUY-11-C/TAKARKUY)")
    @patch(
        "apps.dashboard.maps.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout=b"[]"),
    )
    def test_transport_uses_identity_bounded_output_and_leases_are_released(self, run):
        self.assertEqual(_http("nominatim", "https://nominatim.openstreetmap.org/search"), [])
        request = json.loads(run.call_args.kwargs["input"])
        self.assertIn("TAKARKUY", request["headers"]["User-Agent"])
        self.assertIsNone(MapProviderGate.objects.get().lease)

    def test_json_script_escapes_map_config_and_policy_allows_origin_referer(self):
        with override_settings(MAP_TILE_URL="</script><script>alert(1)</script>"):
            response = self.client.get(reverse("modul5"))
        self.assertNotContains(response, "</script><script>alert(1)</script>")
        self.assertEqual(response["Referrer-Policy"], "strict-origin-when-cross-origin")
