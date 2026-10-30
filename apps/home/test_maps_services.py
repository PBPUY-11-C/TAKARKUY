import json
import runpy
from datetime import timedelta
from hashlib import sha256
from io import StringIO
from unittest.mock import MagicMock, Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from . import map_transport, maps, services
from .models import MapLookupCache, MapProviderGate, MapQuota

User = get_user_model()

IDENTITAS = "TAKARKUY-test/1.0 (https://takarkuy.example.test)"
GEO = "https://geo.example.test/search"
OVERPASS = "https://overpass.example.test/api"
CFG = {
    "MAP_USER_AGENT": IDENTITAS,
    "MAP_GEOCODER_URL": GEO,
    "MAP_OVERPASS_URL": OVERPASS,
    "MAP_LOOKUP_ENABLED": True,
}


def data_kurasi():
    return {
        "reviewed_on": "2026-01-01",
        "places": [
            {
                "id": "a",
                "name": "Pasar Bandung",
                "kind": "market",
                "region": "Bandung",
                "address": "Jl. Aceh",
                "lat": -6.91,
                "lon": 107.61,
            },
            {
                "id": "b",
                "name": "Pasar Surabaya",
                "kind": "market",
                "region": "Surabaya",
                "address": "Jl. Raya",
                "lat": -7.25,
                "lon": 112.75,
            },
            {
                "id": "c",
                "name": "Mal Bandung",
                "kind": "mall",
                "region": "Bandung",
                "address": "Jl. Mal",
                "lat": -6.9,
                "lon": 107.6,
            },
        ],
    }


def hasil_osm():
    return {
        "places": [{"id": "osm-node-1", "name": "Pasar OSM", "lat": -6.9, "lon": 107.6}],
        "center": [-6.9, 107.6],
        "source": "osm",
        "provider": "overpass",
        "message": "",
    }


def proses(returncode=0, stdout=b"{}"):
    return Mock(returncode=returncode, stdout=stdout)


# map_transport.py

class MapTransportTest(SimpleTestCase):
    def opener(self, isi):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = isi
        return opener

    def test_fetch_sukses(self):
        data = {"url": "https://x.test", "headers": {"A": "b"}, "body": "q=1"}
        with patch.object(map_transport, "build_opener", return_value=self.opener(b'{"ok": true}')):
            self.assertEqual(map_transport.fetch(data), {"ok": True})

    def test_fetch_respons_terlalu_besar(self):
        data = {"url": "https://x.test", "headers": {}}
        with patch.object(map_transport, "build_opener", return_value=self.opener(b"x" * 524289)):
            with self.assertRaises(ValueError):
                map_transport.fetch(data)

    def test_tidak_mengikuti_redirect(self):
        hasil = map_transport.NoRedirect().redirect_request(
            None, None, 302, "Found", {}, "https://lain.test"
        )
        self.assertIsNone(hasil)

    def test_main_sukses(self):
        stdin = Mock()
        stdin.buffer.read.return_value = b'{"url": "https://x.test", "headers": {}}'
        keluaran = StringIO()
        with (
            patch("sys.stdin", stdin),
            patch("sys.stdout", keluaran),
            patch("urllib.request.build_opener", return_value=self.opener(b'{"ok": true}')),
        ):
            runpy.run_module("apps.home.map_transport", run_name="__main__")
        self.assertEqual(json.loads(keluaran.getvalue()), {"ok": True})

    def test_main_gagal_keluar_dengan_kode_1(self):
        stdin = Mock()
        stdin.buffer.read.return_value = b"bukan json"
        with patch("sys.stdin", stdin):
            with self.assertRaises(SystemExit) as ctx:
                runpy.run_module("apps.home.map_transport", run_name="__main__")
        self.assertEqual(ctx.exception.code, 1)

# maps.py: fungsi murni

class MapsPureTest(SimpleTestCase):
    def test_endpoint_valid(self):
        self.assertEqual(maps.endpoint("https://a.test/x"), "https://a.test/x")

    def test_endpoint_tidak_valid(self):
        for url in [
            "http://a.test",
            "https://",
            "https://user:pw@a.test",
            "https://user@a.test",
            "https://a.test/#frag",
        ]:
            with self.subTest(url=url):
                with self.assertRaises(maps.MapUnavailable):
                    maps.endpoint(url)

    def test_read_places_file_asli(self):
        data = maps.read_places()
        self.assertIn("places", data)
        self.assertIn("reviewed_on", data)

    def test_normalized_region_valid(self):
        self.assertEqual(maps.normalized_region("Kota  Bandung"), "bandung")
        self.assertEqual(maps.normalized_region("Kabupaten Bogor"), "bogor")
        self.assertEqual(maps.normalized_region("Depok"), "depok")

    def test_normalized_region_tidak_valid(self):
        for nilai in [None, 123, "", "a", "Bandung123", "jalan merdeka", "rumah saya", "kota x"]:
            with self.subTest(nilai=nilai):
                with self.assertRaises(ValueError):
                    maps.normalized_region(nilai)

    def test_distance_km(self):
        self.assertEqual(maps.distance_km((-6.9, 107.6), (-6.9, 107.6)), 0)
        jarak = maps.distance_km((-6.2088, 106.8456), (-6.9175, 107.6191))
        self.assertTrue(100 < jarak < 130)

    def test_nearest_menghapus_duplikat_dan_membatasi(self):
        places = [
            {"name": "Pasar A", "lat": -6.9, "lon": 107.6},
            {"name": "pasar  a", "lat": -6.95, "lon": 107.65},
            {"name": "Pasar B", "lat": -6.8, "lon": 107.5},
        ]
        hasil = maps.nearest(places, (-6.9, 107.6))
        self.assertEqual([p["name"] for p in hasil], ["Pasar A", "Pasar B"])
        self.assertEqual(len(maps.nearest(places, (-6.9, 107.6), limit=1)), 1)

    def test_coordinates(self):
        self.assertEqual(maps.coordinates("-6.9", "107.6"), (-6.9, 107.6))
        for lat, lon in [
            (True, 107.6),
            (-6.9, False),
            ("abc", 107.6),
            (None, None),
            (50, 107.6),
            (-6.9, 10),
            ("nan", 107.6),
            ("inf", 107.6),
        ]:
            with self.subTest(lat=lat, lon=lon):
                self.assertIsNone(maps.coordinates(lat, lon))

    def test_rounded_point(self):
        self.assertEqual(maps.rounded_point(-6.91234, 107.65678), (-6.91, 107.66))
        with self.assertRaises(ValueError):
            maps.rounded_point(50, 10)

    def test_search_request(self):
        self.assertEqual(maps.search_request({"region": "Kota Bandung"}), ("bandung", None))
        self.assertEqual(maps.search_request({"lat": -6.9, "lon": 107.6}), (None, (-6.9, 107.6)))
        for data in [
            "bukan dict",
            {"region": "Bandung", "x": 1},
            {"region": "Bandung", "lat": -6.9, "lon": 107.6},
        ]:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    maps.search_request(data)

    def test_map_limited_retry_after_minimal_1(self):
        self.assertEqual(maps.MapLimited(0).retry_after, 1)
        self.assertEqual(maps.MapLimited(2.1).retry_after, 3)

    def test_osm_place(self):
        place = maps.osm_place("Bandung", "node", 7, "a" * 200, (-6.9, 107.6), "Jl. A")
        self.assertEqual(place["id"], "osm-node-7")
        self.assertEqual(len(place["name"]), 150)
        self.assertEqual(place["source_url"], "https://www.openstreetmap.org/node/7")
        for tipe, osm_id in [("foo", 1), ("node", 0), ("node", True), ("node", "1")]:
            with self.subTest(tipe=tipe, osm_id=osm_id):
                self.assertIsNone(maps.osm_place("x", tipe, osm_id, "n", (1, 2), "a"))


# maps.py: data kurasi

class CuratedTest(SimpleTestCase):
    def test_berdasarkan_wilayah(self):
        with patch.object(maps, "read_places", side_effect=data_kurasi):
            hasil = maps.curated(region="bandung")
        self.assertEqual([p["name"] for p in hasil["places"]], ["Pasar Bandung"])
        self.assertEqual(hasil["source"], "curated")
        self.assertEqual(hasil["message"], "")

    def test_wilayah_tanpa_data(self):
        with patch.object(maps, "read_places", side_effect=data_kurasi):
            hasil = maps.curated(region="medan")
        self.assertEqual(hasil["places"], [])
        self.assertIn("Belum ada data pasar", hasil["message"])

    def test_berdasarkan_titik_hanya_yang_dekat(self):
        with patch.object(maps, "read_places", side_effect=data_kurasi):
            hasil = maps.curated(point=(-6.91, 107.61))
        self.assertEqual([p["name"] for p in hasil["places"]], ["Pasar Bandung"])


# maps.py: kuota

class ReserveMapTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="aiko", password="rahasia123")

    def test_kuota_bertambah(self):
        maps.reserve_map(self.user)
        self.assertEqual(MapQuota.objects.get(user=self.user).attempts, 1)

    def test_kuota_habis_setelah_10_kali(self):
        for _ in range(10):
            maps.reserve_map(self.user)
        with self.assertRaises(maps.MapLimited) as ctx:
            maps.reserve_map(self.user)
        self.assertGreaterEqual(ctx.exception.retry_after, 1)

    def test_kuota_reset_setelah_10_menit(self):
        for _ in range(10):
            maps.reserve_map(self.user)
        MapQuota.objects.filter(user=self.user).update(
            window_started_at=timezone.now() - timedelta(minutes=11)
        )
        maps.reserve_map(self.user)
        self.assertEqual(MapQuota.objects.get(user=self.user).attempts, 1)

# maps.py: _http

@override_settings(**CFG)
class HttpTest(TestCase):
    def test_identitas_kosong(self):
        with override_settings(MAP_USER_AGENT=""):
            with self.assertRaises(maps.MapUnavailable):
                maps._http("overpass", OVERPASS)

    def test_identitas_tanpa_nama_aplikasi(self):
        with override_settings(MAP_USER_AGENT="Bot/1.0 (https://a.test)"):
            with self.assertRaises(maps.MapUnavailable):
                maps._http("overpass", OVERPASS)

    def test_sukses(self):
        with patch.object(maps.subprocess, "run", return_value=proses(stdout=b'{"ok": 1}')) as run:
            hasil = maps._http("overpass", OVERPASS, "q=1")
        self.assertEqual(hasil, {"ok": 1})
        kiriman = json.loads(run.call_args.kwargs["input"])
        self.assertEqual(kiriman["url"], OVERPASS)
        self.assertEqual(kiriman["body"], "q=1")

    def test_proses_gagal(self):
        with patch.object(maps.subprocess, "run", return_value=proses(returncode=1)):
            with self.assertRaises(maps.MapUnavailable):
                maps._http("overpass", OVERPASS)

    def test_keluaran_terlalu_besar(self):
        with patch.object(maps.subprocess, "run", return_value=proses(stdout=b"x" * 524289)):
            with self.assertRaises(maps.MapUnavailable):
                maps._http("overpass", OVERPASS)

    def test_keluaran_bukan_json(self):
        with patch.object(maps.subprocess, "run", return_value=proses(stdout=b"bukan json")):
            with self.assertRaises(maps.MapUnavailable):
                maps._http("overpass", OVERPASS)

    def test_timeout(self):
        error = maps.subprocess.TimeoutExpired(cmd="x", timeout=8)
        with patch.object(maps.subprocess, "run", side_effect=error):
            with self.assertRaises(maps.MapUnavailable):
                maps._http("overpass", OVERPASS)

    def test_gerbang_sibuk_dan_tidak_mau_menunggu(self):
        now = timezone.now()
        key = sha256(b"overpass").hexdigest()
        MapProviderGate.objects.create(
            key=key,
            next_at=now + timedelta(seconds=60),
            lease_until=now + timedelta(seconds=60),
        )
        with self.assertRaises(maps.MapLimited):
            maps._http("overpass", OVERPASS, max_wait=0)

    def test_gerbang_masih_sibuk_setelah_menunggu(self):
        now = timezone.now()
        key = sha256(b"overpass").hexdigest()
        MapProviderGate.objects.create(
            key=key,
            next_at=now + timedelta(seconds=0.5),
            lease_until=now + timedelta(seconds=0.5),
        )
        with patch.object(maps.time, "sleep") as sleep:
            with self.assertRaises(maps.MapLimited):
                maps._http("overpass", OVERPASS, max_wait=1)
        self.assertEqual(sleep.call_count, 2)

    def test_menunggu_lalu_berhasil(self):
        now = timezone.now()
        key = sha256(b"overpass").hexdigest()
        MapProviderGate.objects.create(
            key=key,
            next_at=now + timedelta(seconds=0.5),
            lease_until=now + timedelta(seconds=0.5),
        )

        def buka_gerbang(_detik):
            lalu = timezone.now() - timedelta(seconds=5)
            MapProviderGate.objects.filter(pk=key).update(next_at=lalu, lease_until=lalu)

        with (
            patch.object(maps.time, "sleep", side_effect=buka_gerbang) as sleep,
            patch.object(maps.subprocess, "run", return_value=proses(stdout=b'{"ok": 1}')),
        ):
            hasil = maps._http("overpass", OVERPASS, max_wait=1)
        self.assertEqual(hasil, {"ok": 1})
        sleep.assert_called_once()

# maps.py: geocode_region

@override_settings(**CFG)
class GeocodeRegionTest(TestCase):
    def test_sukses_lalu_dari_cache(self):
        areas = [{"addresstype": "city", "lat": "-6.9", "lon": "107.6"}]
        with patch.object(maps, "_http", return_value=areas) as http:
            self.assertEqual(maps.geocode_region("bandung"), (-6.9, 107.6))
            self.assertEqual(maps.geocode_region("bandung"), (-6.9, 107.6))
        self.assertEqual(http.call_count, 1)

    def test_tidak_ditemukan_juga_di_cache(self):
        with patch.object(maps, "_http", return_value=[]) as http:
            self.assertIsNone(maps.geocode_region("xyzzy"))
            self.assertIsNone(maps.geocode_region("xyzzy"))
        self.assertEqual(http.call_count, 1)

    def test_respons_bukan_list(self):
        with patch.object(maps, "_http", return_value={"a": 1}):
            with self.assertRaises(maps.MapUnavailable):
                maps.geocode_region("bandung")

    def test_hasil_bukan_dict(self):
        with patch.object(maps, "_http", return_value=["teks"]):
            with self.assertRaises(maps.MapUnavailable):
                maps.geocode_region("bandung")

    def test_bukan_wilayah_administratif(self):
        areas = [{"addresstype": "shop", "lat": "-6.9", "lon": "107.6"}]
        with patch.object(maps, "_http", return_value=areas):
            with self.assertRaises(maps.MapUnavailable):
                maps.geocode_region("bandung")

    def test_koordinat_tidak_valid(self):
        areas = [{"addresstype": "city", "lat": "99", "lon": "10"}]
        with patch.object(maps, "_http", return_value=areas):
            with self.assertRaises(maps.MapUnavailable):
                maps.geocode_region("bandung")


# ======================================================================
# maps.py: overpass, nominatim, osm_markets
# ======================================================================
@override_settings(**CFG)
class OsmParsingTest(TestCase):
    def test_overpass_hanya_ambil_yang_valid(self):
        elemen_valid = {
            "type": "node",
            "id": 1,
            "lat": -6.9,
            "lon": 107.6,
            "tags": {"name": "Pasar Baru", "amenity": "marketplace", "addr:street": "Jl. Baru"},
        }
        elemen_center = {
            "type": "way",
            "id": 2,
            "center": {"lat": -6.91, "lon": 107.61},
            "tags": {"name": "Pasar Lama", "amenity": "marketplace"},
        }
        tidak_valid = [
            "bukan dict",
            {"tags": "bukan dict"},
            {
                "type": "node",
                "id": 3,
                "lat": -6.9,
                "lon": 107.6,
                "tags": {"amenity": "marketplace"},
            },
            {
                "type": "node",
                "id": 4,
                "lat": -6.9,
                "lon": 107.6,
                "tags": {"name": "Toko", "amenity": "shop"},
            },
            {
                "type": "node",
                "id": 5,
                "lat": 50,
                "lon": 10,
                "tags": {"name": "Jauh", "amenity": "marketplace"},
            },
            {
                "type": "foo",
                "id": 6,
                "lat": -6.9,
                "lon": 107.6,
                "tags": {"name": "Aneh", "amenity": "marketplace"},
            },
        ]
        hasil = {"elements": [elemen_valid, elemen_center, *tidak_valid]}
        with patch.object(maps, "_http", return_value=hasil):
            places = maps.overpass_markets("Bandung", (-7, 107, -6, 108))
        self.assertEqual([p["name"] for p in places], ["Pasar Baru", "Pasar Lama"])
        self.assertEqual(places[0]["address"], "Jl. Baru")

    def test_overpass_respons_tidak_valid(self):
        for hasil in [
            "bukan dict",
            {"elements": "bukan list"},
            {"elements": [], "remark": "timeout"},
        ]:
            with self.subTest(hasil=hasil):
                with patch.object(maps, "_http", return_value=hasil):
                    with self.assertRaises(maps.MapUnavailable):
                        maps.overpass_markets("Bandung", (-7, 107, -6, 108))

    def test_nominatim_hanya_ambil_yang_valid(self):
        valid = {
            "name": "Pasar Lama",
            "category": "amenity",
            "type": "marketplace",
            "lat": "-6.9",
            "lon": "107.6",
            "osm_type": "node",
            "osm_id": 5,
            "display_name": "Pasar Lama, Jl. A, Kel. B, Bandung",
        }
        tidak_valid = [
            "bukan dict",
            {**valid, "name": ""},
            {**valid, "name": 123},
            {**valid, "category": "shop"},
            {**valid, "lat": "99"},
            {**valid, "osm_type": "foo"},
        ]
        with patch.object(maps, "_http", return_value=[valid, *tidak_valid]):
            places = maps.nominatim_markets("Bandung", (-7, 107, -6, 108))
        self.assertEqual(len(places), 1)
        self.assertEqual(places[0]["address"], "Jl. A, Kel. B")

    def test_nominatim_respons_bukan_list(self):
        with patch.object(maps, "_http", return_value={"a": 1}):
            with self.assertRaises(maps.MapUnavailable):
                maps.nominatim_markets("Bandung", (-7, 107, -6, 108))

    def test_osm_markets_pakai_overpass(self):
        place = {"name": "Pasar A", "lat": -6.9, "lon": 107.6}
        with patch.object(maps, "overpass_markets", return_value=[place]):
            hasil = maps.osm_markets((-6.9, 107.6), "Bandung")
        self.assertEqual(hasil["provider"], "overpass")
        self.assertEqual(len(hasil["places"]), 1)
        self.assertEqual(hasil["message"], "")

    def test_osm_markets_fallback_ke_nominatim(self):
        for error in [maps.MapUnavailable("x"), maps.MapLimited(1)]:
            with self.subTest(error=type(error).__name__):
                with (
                    patch.object(maps, "overpass_markets", side_effect=error),
                    patch.object(maps, "nominatim_markets", return_value=[]),
                ):
                    hasil = maps.osm_markets((-6.9, 107.6), "Bandung")
                self.assertEqual(hasil["provider"], "nominatim")
                self.assertIn("Belum ada pasar", hasil["message"])

# maps.py: lookup_places

@override_settings(**CFG)
class LookupPlacesTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="aiko", password="rahasia123")
        patcher = patch.object(maps, "read_places", side_effect=data_kurasi)
        patcher.start()
        self.addCleanup(patcher.stop)

    @override_settings(MAP_LOOKUP_ENABLED=False)
    def test_pencarian_nonaktif_dengan_data_kurasi(self):
        hasil = maps.lookup_places(self.user, {"region": "Bandung"})
        self.assertEqual(hasil["source"], "curated")
        self.assertIn("belum diaktifkan", hasil["message"])
        self.assertIn("Menampilkan data kurasi", hasil["message"])

    @override_settings(MAP_LOOKUP_ENABLED=False)
    def test_pencarian_nonaktif_tanpa_data_kurasi(self):
        hasil = maps.lookup_places(self.user, {"region": "Medan"})
        self.assertEqual(hasil["places"], [])
        self.assertIn("Belum ada data pasar", hasil["message"])

    def test_input_tidak_valid(self):
        with self.assertRaises(ValueError):
            maps.lookup_places(self.user, {"region": "jalan merdeka"})

    def test_wilayah_sukses_lalu_dari_cache(self):
        with (
            patch.object(maps, "geocode_region", return_value=(-6.9, 107.6)),
            patch.object(maps, "osm_markets", return_value=hasil_osm()) as osm,
        ):
            pertama = maps.lookup_places(self.user, {"region": "Bandung"})
            kedua = maps.lookup_places(self.user, {"region": "Bandung"})
        self.assertEqual(pertama["places"][0]["name"], "Pasar OSM")
        self.assertTrue(kedua["cached"])
        self.assertEqual(osm.call_count, 1)

    def test_titik_lokasi(self):
        with patch.object(maps, "osm_markets", return_value=hasil_osm()) as osm:
            hasil = maps.lookup_places(self.user, {"lat": -6.9, "lon": 107.6})
        osm.assert_called_once_with((-6.9, 107.6), "Sekitar lokasi Anda")
        self.assertEqual(hasil["source"], "osm")

    def test_wilayah_tidak_ditemukan(self):
        with patch.object(maps, "geocode_region", return_value=None):
            hasil = maps.lookup_places(self.user, {"region": "Medan"})
        self.assertEqual(hasil["message"], "Wilayah tidak ditemukan.")
        self.assertEqual(hasil["places"], [])

    def test_hasil_daring_kosong_pakai_data_kurasi(self):
        with patch.object(maps, "geocode_region", return_value=None):
            hasil = maps.lookup_places(self.user, {"region": "Bandung"})
        self.assertEqual(hasil["source"], "curated")
        self.assertIn("Hasil daring kosong", hasil["message"])

    def test_layanan_sibuk(self):
        with (
            patch.object(maps, "geocode_region", return_value=(-6.9, 107.6)),
            patch.object(maps, "osm_markets", side_effect=maps.MapLimited(2.2)),
        ):
            hasil = maps.lookup_places(self.user, {"region": "Bandung"})
        self.assertEqual(hasil["retry_after"], 3)
        self.assertIn("sedang sibuk", hasil["message"])
        self.assertEqual(hasil["source"], "curated")

    def test_layanan_tidak_tersedia(self):
        with (
            patch.object(maps, "geocode_region", return_value=(-6.9, 107.6)),
            patch.object(maps, "osm_markets", side_effect=maps.MapUnavailable("x")),
        ):
            hasil = maps.lookup_places(self.user, {"region": "Bandung"})
        self.assertIn("tidak tersedia", hasil["message"])
        self.assertEqual(hasil["source"], "curated")

    def test_kuota_habis(self):
        MapQuota.objects.create(user=self.user, window_started_at=timezone.now(), attempts=10)
        with self.assertRaises(maps.MapLimited):
            maps.lookup_places(self.user, {"region": "Bandung"})

    def test_cache_kedaluwarsa_dibersihkan(self):
        MapLookupCache.objects.update_or_create(
            pk="kunci-lama",
            defaults={"payload": {}, "expires_at": timezone.now() - timedelta(days=8)},
        )
        with (
            patch.object(maps, "geocode_region", return_value=(-6.9, 107.6)),
            patch.object(maps, "osm_markets", return_value=hasil_osm()),
        ):
            maps.lookup_places(self.user, {"region": "Bandung"})
        self.assertFalse(MapLookupCache.objects.filter(pk="kunci-lama").exists())


# services.py

class ServicesTest(TestCase):
    def test_parse_money_valid(self):
        self.assertEqual(services.parse_money("15000"), 15000)
        self.assertEqual(services.parse_money(1000), 1000)
        self.assertEqual(str(services.parse_money(12.5)), "12.5")
        self.assertEqual(services.parse_money(0), 0)

    def test_parse_money_tidak_valid(self):
        for nilai in [True, None, [], {}, "abc", "-5", "1e15", "NaN", "inf"]:
            with self.subTest(nilai=nilai):
                self.assertIsNone(services.parse_money(nilai))

    def test_staple_suffix(self):
        with patch("apps.home.services.meal_staple", return_value={"label": "Nasi"}):
            self.assertEqual(services.staple_suffix({}), " + Nasi")
        with patch("apps.home.services.meal_staple", return_value=None):
            self.assertEqual(services.staple_suffix({}), "")

    def test_dashboard_data_user_tanpa_data(self):
        user = User.objects.create_user(username="aiko", password="rahasia123")
        data = services.dashboard_data(user)
        self.assertEqual(len(data["week"]), 7)
        self.assertFalse(data["week_has_meals"])
        self.assertEqual(data["plans"], [])
        self.assertEqual(data["stock_counts"]["total"], 0)
        self.assertEqual(data["cooking_count"], 0)
        self.assertEqual(data["recent_cooking"], [])
        self.assertIsNone(data["unsaved_draft"])
