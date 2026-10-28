import json
import subprocess
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.home.maps import (
    MapLimited,
    MapUnavailable,
    _http,
    curated,
    geocode_region,
    osm_markets,
    read_places,
)
from apps.home.models import MapLookupCache, MapProviderGate, MapQuota


class MapTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("petaku")
        self.client.force_login(self.user)
        geocode = patch("apps.home.maps.geocode_region", return_value=(-7.2, 107.9))
        geocode.start()
        self.addCleanup(geocode.stop)

    def post(self, **changes):
        return self.client.post(
            reverse("modul5-places"),
            json.dumps({"region": "Garut", **changes}),
            content_type="application/json",
        )

    def post_point(self, lat=-7.2012, lon=107.9049):
        return self.client.post(
            reverse("modul5-places"),
            json.dumps({"lat": lat, "lon": lon}),
            content_type="application/json",
        )

    @patch("apps.home.maps.osm_markets")
    def test_curated_fallback_is_markets_only_with_sources(self, provider):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["places"]), 3)
        provider.assert_not_called()
        for place in read_places()["places"]:
            self.assertEqual(place["kind"], "market")
            self.assertTrue(place["source_url"].startswith("https://"))

    def test_curated_point_fallback_is_sorted_and_limited_to_nearby(self):
        places = curated(point=(-7.09, 107.9))["places"]
        self.assertEqual(places[0]["name"], "Pasar Kadungora")
        self.assertEqual(
            [p["distance_km"] for p in places], sorted(p["distance_km"] for p in places)
        )
        self.assertEqual(curated(point=(-6.4, 106.82))["places"], [])

    def test_missing_area_is_honest_not_demo_places(self):
        response = self.post(region="Jayapura")
        self.assertEqual(response.json()["places"], [])
        self.assertIn("Belum ada data pasar", response.json()["message"])

    def test_invalid_locations_addresses_and_extra_fields_rejected(self):
        for data in (
            {"lat": -6.3},
            {"lat": 51.5, "lon": -0.12},
            {"lat": True, "lon": 106.8},
            {"lat": "nan", "lon": 106.8},
            {"lat": -6.3, "lon": 106.8, "region": "Depok"},
            {"region": "person@example.com"},
            {"region": "Jl Rumah 123"},
            {"region": {}},
            {"region": " "},
            {"region": "Depok", "kind": "market"},
            {"region": "Depok", "online": True},
        ):
            with self.subTest(data=data):
                response = self.client.post(
                    reverse("modul5-places"), json.dumps(data), content_type="application/json"
                )
                self.assertEqual(response.status_code, 400)
        self.assertEqual(MapLookupCache.objects.count(), 0)

    @override_settings(MAP_LOOKUP_ENABLED=True)
    @patch("apps.home.maps.osm_markets")
    def test_location_is_rounded_before_search_and_cache(self, provider):
        provider.return_value = {"places": [{"name": "Pasar OSM"}], "source": "osm", "message": ""}
        self.assertEqual(self.post_point().status_code, 200)
        self.assertEqual(provider.call_args.args[0], (-7.2, 107.9))
        self.assertTrue(self.post_point(-7.1989, 107.8971).json()["cached"])
        self.assertEqual(provider.call_count, 1)
        cache = MapLookupCache.objects.get()
        self.assertNotIn("7.2012", json.dumps(cache.payload))
        self.assertNotIn("user", cache.payload)

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
    @patch("apps.home.maps.osm_markets")
    def test_online_is_operator_opt_in(self, provider):
        result = self.post().json()
        self.assertEqual(result["source"], "curated")
        self.assertIn("belum diaktifkan", result["message"])
        provider.assert_not_called()
        self.assertFalse(MapQuota.objects.exists())

    @override_settings(MAP_LOOKUP_ENABLED=True)
    @patch(
        "apps.home.maps.osm_markets",
        return_value={"places": [], "source": "osm", "message": "Data belum tersedia"},
    )
    def test_empty_online_results_fall_back_to_curated(self, provider):
        self.assertEqual(self.post().json()["source"], "curated")

    @override_settings(MAP_LOOKUP_ENABLED=True)
    @patch("apps.home.maps.osm_markets")
    def test_shared_cache_serves_other_accounts_without_second_provider_call(self, provider):
        provider.return_value = {"places": [{"name": "Pasar OSM"}], "source": "osm", "message": ""}
        self.assertEqual(self.post().status_code, 200)
        self.client.force_login(get_user_model().objects.create_user("petamu"))
        second = self.post(region=" GARUT ").json()
        self.assertTrue(second["cached"])
        self.assertEqual(provider.call_count, 1)
        cache = MapLookupCache.objects.get()
        self.assertEqual(len(cache.key), 64)
        self.assertNotIn("user", cache.payload)
        self.assertNotIn("gps", cache.payload)

    @override_settings(MAP_LOOKUP_ENABLED=True)
    @patch("apps.home.maps.osm_markets", side_effect=MapUnavailable("timeout"))
    def test_provider_failure_returns_curated_not_500(self, provider):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "curated")
        self.assertFalse(MapLookupCache.objects.exists())

    @override_settings(MAP_LOOKUP_ENABLED=True)
    @patch("apps.home.maps.osm_markets", side_effect=MapLimited(2))
    def test_provider_busy_returns_curated_without_retry_loop(self, provider):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "curated")
        self.assertEqual(response.json()["retry_after"], 2)
        self.assertEqual(len(response.json()["places"]), 3)
        self.assertIn("sedang sibuk", response.json()["message"])
        self.assertFalse(MapLookupCache.objects.exists())
        self.assertEqual(provider.call_count, 1)

    @override_settings(MAP_LOOKUP_ENABLED=True)
    @patch("apps.home.maps.osm_markets")
    def test_account_quota_survives_another_client(self, provider):
        provider.return_value = {"places": [{"name": "Pasar OSM"}], "source": "osm", "message": ""}
        for _ in range(10):
            self.assertEqual(self.post().status_code, 200)
        client = Client()
        client.force_login(self.user)
        response = client.post(
            reverse("modul5-places"),
            json.dumps({"region": "Garut"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response["Retry-After"]), 0)
        self.assertEqual(provider.call_count, 1)
        MapQuota.objects.update(window_started_at=timezone.now() - timedelta(minutes=11))
        self.assertEqual(self.post().status_code, 200)

    @patch("apps.home.maps._http")
    def test_overpass_keeps_named_markets_only_nearest_first(self, http):
        http.return_value = {
            "elements": [
                {
                    "type": "way",
                    "id": 2,
                    "center": {"lat": -7.25, "lon": 107.9},
                    "tags": {"name": "Pasar Jauh", "amenity": "marketplace"},
                },
                {
                    "type": "node",
                    "id": 1,
                    "lat": -7.201,
                    "lon": 107.9,
                    "tags": {"name": "Pasar Dekat", "amenity": "marketplace"},
                },
                {
                    "type": "node",
                    "id": 6,
                    "lat": -7.251,
                    "lon": 107.9,
                    "tags": {"name": "pasar  jauh", "amenity": "marketplace"},
                },
                {
                    "type": "node",
                    "id": 3,
                    "lat": -7.2,
                    "lon": 107.9,
                    "tags": {"name": "Bank Sampah Bersih", "amenity": "recycling"},
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
        }
        result = osm_markets((-7.2, 107.9), "Sekitar lokasi Anda")
        self.assertEqual([p["name"] for p in result["places"]], ["Pasar Dekat", "Pasar Jauh"])
        self.assertLess(result["places"][0]["distance_km"], 1)
        self.assertEqual(result["provider"], "overpass")
        self.assertEqual(http.call_count, 1)
        self.assertIn("out+center+40", http.call_args.args[2])

    @patch("apps.home.maps._http")
    def test_busy_overpass_falls_back_to_nominatim_markets(self, http):
        http.side_effect = [
            MapUnavailable("Overpass penuh"),
            [
                {
                    "name": "Pasar Depok Jaya",
                    "category": "amenity",
                    "type": "marketplace",
                    "lat": "-6.39",
                    "lon": "106.82",
                    "osm_type": "way",
                    "osm_id": 42,
                    "display_name": "Pasar Depok Jaya, Jalan Nusantara, Depok, Jawa Barat",
                },
                {
                    "name": "Kelurahan Pasar",
                    "category": "place",
                    "type": "village",
                    "lat": "-6.4",
                    "lon": "106.8",
                    "osm_type": "node",
                    "osm_id": 7,
                },
            ],
        ]
        result = osm_markets((-6.4, 106.82), "Sekitar lokasi Anda")
        self.assertEqual(result["provider"], "nominatim")
        self.assertEqual([p["name"] for p in result["places"]], ["Pasar Depok Jaya"])
        self.assertEqual(result["places"][0]["source_url"], "https://www.openstreetmap.org/way/42")
        calls = http.call_args_list
        self.assertEqual([c.args[0] for c in calls], ["overpass", "nominatim"])
        self.assertIn("%5Bmarketplace%5D", calls[1].args[1])
        self.assertEqual(calls[1].kwargs["max_wait"], 1.5)

    @override_settings(MAP_LOOKUP_ENABLED=True)
    @patch("apps.home.maps.osm_markets")
    def test_region_search_uses_geocoded_center(self, provider):
        provider.return_value = {"places": [{"name": "Pasar OSM"}], "source": "osm", "message": ""}
        self.post(region="Kota Depok")
        self.assertEqual(provider.call_args.args[:2], ((-7.2, 107.9), "Depok"))
        self.assertEqual(provider.call_args.kwargs["radius"], 0.08)

    @patch("apps.home.maps._http")
    def test_geocoder_rejects_non_administrative_result(self, http):
        http.return_value = [{"lat": "-7.2", "lon": "107.9", "addresstype": "road"}]
        with self.assertRaises(MapUnavailable):
            geocode_region("garut")
        self.assertFalse(MapLookupCache.objects.exists())

    @override_settings(MAP_USER_AGENT="TAKARKUY/1.0 (+https://github.com/PBPUY-11-C/TAKARKUY)")
    @patch("apps.home.maps.subprocess.run")
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
    @patch("apps.home.maps.subprocess.run")
    def test_no_identifying_agent_means_no_outbound_request(self, run):
        with self.assertRaises(MapUnavailable):
            _http("nominatim", "https://nominatim.openstreetmap.org/search")
        run.assert_not_called()

    @override_settings(MAP_USER_AGENT="TAKARKUY/1.0 (+https://github.com/PBPUY-11-C/TAKARKUY)")
    @patch(
        "apps.home.maps.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout=b"[]"),
    )
    def test_transport_uses_identity_bounded_output_and_leases_are_released(self, run):
        self.assertEqual(_http("nominatim", "https://nominatim.openstreetmap.org/search"), [])
        request = json.loads(run.call_args.kwargs["input"])
        self.assertIn("TAKARKUY", request["headers"]["User-Agent"])
        self.assertIsNone(MapProviderGate.objects.get().lease)
