"""Nearest-market search from a rounded location or a region name, with a curated fallback."""

import hashlib
import json
import math
import re
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import MapLookupCache, MapProviderGate, MapQuota

NEAR_KM = 30


class MapUnavailable(ValueError):
    pass


class MapLimited(ValueError):
    def __init__(self, retry_after):
        self.retry_after = max(1, math.ceil(retry_after))
        super().__init__("Pencarian sedang dibatasi. Coba lagi sebentar.")


def endpoint(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise MapUnavailable("Penyedia peta belum dikonfigurasi dengan benar.")
    return value


def read_places():
    return json.loads(Path(__file__).with_name("places.json").read_text(encoding="utf-8"))


def normalized_region(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z .'-]{2,60}", value):
        raise ValueError("Masukkan nama kota atau kabupaten, bukan alamat pribadi/koordinat.")
    region = " ".join(value.casefold().split())
    region = re.sub(r"^(kota|kabupaten)\s+", "", region)
    if re.search(r"\b(jalan|jl|gang|gg|rumah|rt|rw)\b", region):
        raise ValueError("Gunakan nama kota/kabupaten, bukan alamat pribadi.")
    if len(region) < 2:
        raise ValueError("Nama wilayah terlalu pendek.")
    return region


def distance_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 6371 * 2 * math.asin(min(1, math.sqrt(h)))


def nearest(places, center, limit=20):
    for place in places:
        place["distance_km"] = round(distance_km(center, (place["lat"], place["lon"])), 2)
    unique, seen = [], set()
    for place in sorted(places, key=lambda place: place["distance_km"]):
        name = " ".join(place["name"].casefold().split())
        if name not in seen:
            seen.add(name)
            unique.append(place)
    return unique[:limit]


def curated(region=None, point=None):
    data = read_places()
    markets = [place for place in data["places"] if place["kind"] == "market"]
    if point:
        places = nearest(
            [dict(place) for place in markets if coordinates(place["lat"], place["lon"])], point
        )
        places = [place for place in places if place["distance_km"] <= NEAR_KM]
    else:
        query = normalized_region(region)
        places = [
            place
            for place in markets
            if query in place["region"].casefold() or query in place["address"].casefold()
        ]
    return {
        "places": places,
        "source": "curated",
        "reviewed_on": data["reviewed_on"],
        "message": "" if places else "Belum ada data pasar di sekitar sini.",
    }


@transaction.atomic
def reserve_map(user):
    get_user_model().objects.select_for_update().get(pk=user.pk)
    now = timezone.now()
    quota, _ = MapQuota.objects.get_or_create(user=user, defaults={"window_started_at": now})
    if quota.window_started_at <= now - timedelta(minutes=10):
        quota.window_started_at, quota.attempts = now, 0
    if quota.attempts >= 10:
        raise MapLimited((quota.window_started_at + timedelta(minutes=10) - now).total_seconds())
    quota.attempts += 1
    quota.save()


def _http(provider, url, body="", max_wait=0):
    identity = settings.MAP_USER_AGENT
    if not identity or "TAKARKUY" not in identity or not re.search(r"https://|@", identity):
        raise MapUnavailable("Identitas aplikasi peta belum diatur.")
    url = endpoint(url)
    key = hashlib.sha256(provider.encode()).hexdigest()
    token = uuid4()
    for _attempt in range(2):
        now = timezone.now()
        with transaction.atomic():
            gate, _ = MapProviderGate.objects.get_or_create(
                key=key, defaults={"next_at": now, "lease_until": now}
            )
            gate = MapProviderGate.objects.select_for_update().get(pk=gate.pk)
            wait = max(
                (gate.next_at - now).total_seconds(), (gate.lease_until - now).total_seconds()
            )
            if wait <= 0:
                gate.next_at = now + timedelta(seconds=1.1)
                gate.lease_until, gate.lease = now + timedelta(seconds=12), token
                gate.save()
                break
        if wait > max_wait:
            raise MapLimited(wait)
        time.sleep(wait)
    else:
        raise MapLimited(1.1)
    try:
        request = {
            "url": url,
            "body": body,
            "headers": {
                "User-Agent": identity,
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        }
        process = subprocess.run(
            [sys.executable, "-m", "apps.home.map_transport"],
            input=json.dumps(request).encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=settings.BASE_DIR,
            timeout=8,
            check=False,
        )
        if process.returncode or len(process.stdout) > 524288:
            raise MapUnavailable("Layanan peta tidak tersedia.")
        return json.loads(process.stdout)
    except (OSError, ValueError, RecursionError, subprocess.TimeoutExpired) as exc:
        raise MapUnavailable("Layanan peta tidak tersedia.") from exc
    finally:
        MapProviderGate.objects.filter(pk=key, lease=token).update(
            lease=None, lease_until=timezone.now(), next_at=timezone.now() + timedelta(seconds=1.1)
        )


def coordinates(lat, lon):
    if isinstance(lat, bool) or isinstance(lon, bool):
        return None
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    return (
        (lat, lon)
        if math.isfinite(lat) and math.isfinite(lon) and -11 <= lat <= 6 and 95 <= lon <= 141
        else None
    )


def geocode_region(region):
    key = hashlib.sha256(
        json.dumps(["region-v1", region, settings.MAP_GEOCODER_URL]).encode()
    ).hexdigest()
    cached = MapLookupCache.objects.filter(pk=key, expires_at__gt=timezone.now()).first()
    if cached and isinstance(cached.payload, dict):
        point = cached.payload.get("center")
        if point is None:
            return None
        if isinstance(point, list) and len(point) == 2 and coordinates(*point):
            return coordinates(*point)
    params = urlencode(
        {"q": f"{region}, Indonesia", "format": "jsonv2", "countrycodes": "id", "limit": 1}
    )
    areas = _http("nominatim", endpoint(settings.MAP_GEOCODER_URL) + "?" + params)
    if not isinstance(areas, list):
        raise MapUnavailable("Hasil wilayah tidak valid.")
    if not areas:
        MapLookupCache.objects.update_or_create(
            pk=key,
            defaults={
                "payload": {"center": None},
                "expires_at": timezone.now() + timedelta(days=1),
            },
        )
        return None
    if not isinstance(areas[0], dict) or areas[0].get("addresstype") not in {
        "city",
        "town",
        "municipality",
        "county",
        "state",
        "city_district",
        "district",
        "administrative",
    }:
        raise MapUnavailable("Hasil pencarian bukan wilayah administratif.")
    center = coordinates(areas[0].get("lat"), areas[0].get("lon"))
    if center is None:
        raise MapUnavailable("Lokasi wilayah tidak valid.")
    MapLookupCache.objects.update_or_create(
        pk=key,
        defaults={
            "payload": {"center": list(center)},
            "expires_at": timezone.now() + timedelta(days=7),
        },
    )
    return center


def rounded_point(lat, lon):
    point = coordinates(lat, lon)
    if point is None:
        raise ValueError("Lokasi di luar Indonesia atau tidak valid.")
    return round(point[0], 2), round(point[1], 2)


def osm_markets(center, label, radius=0.05):
    """Markets around a point from Overpass, or Nominatim when Overpass fails, nearest first."""
    lat, lon = center
    box = (
        max(-11, lat - radius),
        max(95, lon - radius),
        min(6, lat + radius),
        min(141, lon + radius),
    )
    try:
        places, provider = overpass_markets(label, box), "overpass"
    except (MapUnavailable, MapLimited):
        places, provider = nominatim_markets(label, box), "nominatim"
    places = nearest(places, center)
    return {
        "places": places,
        "center": list(center),
        "source": "osm",
        "provider": provider,
        "message": "" if places else "Belum ada pasar tercatat di OpenStreetMap sekitar sini.",
    }


def osm_place(label, osm_type, osm_id, name, point, address):
    if osm_type not in {"node", "way", "relation"} or type(osm_id) is not int or osm_id < 1:
        return None
    return {
        "id": f"osm-{osm_type}-{osm_id}",
        "name": name[:150],
        "kind": "market",
        "region": label,
        "address": address[:200],
        "lat": point[0],
        "lon": point[1],
        "source_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
        "note": "Data komunitas OSM; konfirmasi jam buka sebelum datang.",
    }


def overpass_markets(label, box):
    bbox = ",".join(str(value) for value in box)
    result = _http(
        "overpass",
        endpoint(settings.MAP_OVERPASS_URL),
        urlencode(
            {"data": f'[out:json][timeout:5];nwr["amenity"="marketplace"]({bbox});out center 40;'}
        ),
    )
    if not isinstance(result, dict) or not isinstance(result.get("elements"), list):
        raise MapUnavailable("Hasil peta tidak valid.")
    if result.get("remark"):
        raise MapUnavailable("Pencarian peta belum lengkap.")
    places = []
    for element in result["elements"][:40]:
        if not isinstance(element, dict):
            continue
        tags = element.get("tags", {})
        if (
            not isinstance(tags, dict)
            or not isinstance(tags.get("name"), str)
            or tags.get("amenity") != "marketplace"
        ):
            continue
        position = element.get("center", element)
        point = (
            coordinates(position.get("lat"), position.get("lon"))
            if isinstance(position, dict)
            else None
        )
        if point is None:
            continue
        place = osm_place(
            label,
            element.get("type"),
            element.get("id"),
            tags["name"],
            point,
            str(tags.get("addr:street", "")),
        )
        if place:
            places.append(place)
    return places


def nominatim_markets(label, box):
    south, west, north, east = box
    params = urlencode(
        {
            "q": "[marketplace]",
            "viewbox": f"{west},{north},{east},{south}",
            "bounded": 1,
            "format": "jsonv2",
            "countrycodes": "id",
            "limit": 40,
        }
    )
    rows = _http("nominatim", endpoint(settings.MAP_GEOCODER_URL) + "?" + params, max_wait=1.5)
    if not isinstance(rows, list):
        raise MapUnavailable("Hasil peta tidak valid.")
    places = []
    for row in rows[:40]:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"]:
            continue
        if (row.get("category"), row.get("type")) != ("amenity", "marketplace"):
            continue
        point = coordinates(row.get("lat"), row.get("lon"))
        if point is None:
            continue
        address = ", ".join(str(row.get("display_name", "")).split(", ")[1:3])
        place = osm_place(
            label, row.get("osm_type"), row.get("osm_id"), row["name"], point, address
        )
        if place:
            places.append(place)
    return places


def search_request(data):
    if not isinstance(data, dict) or set(data) - {"region", "lat", "lon"}:
        raise ValueError("Kirim lokasi atau nama wilayah saja.")
    if "lat" in data or "lon" in data:
        if "region" in data:
            raise ValueError("Pilih salah satu: lokasi atau nama wilayah.")
        return None, rounded_point(data.get("lat"), data.get("lon"))
    return normalized_region(data.get("region")), None


def lookup_places(user, data):
    region, point = search_request(data)
    fallback = curated(region, point)
    if not settings.MAP_LOOKUP_ENABLED:
        return {
            **fallback,
            "message": "Pencarian daring belum diaktifkan. "
            + ("Menampilkan data kurasi." if fallback["places"] else fallback["message"]),
        }
    reserve_map(user)
    target = ["point", *point] if point else ["region", region]
    key = hashlib.sha256(
        json.dumps(
            ["maps-v2", *target, settings.MAP_GEOCODER_URL, settings.MAP_OVERPASS_URL]
        ).encode()
    ).hexdigest()
    cached = MapLookupCache.objects.filter(pk=key, expires_at__gt=timezone.now()).first()
    if cached:
        return {**cached.payload, "cached": True}
    try:
        if point:
            result = osm_markets(point, "Sekitar lokasi Anda")
        else:
            center = geocode_region(region)
            result = (
                osm_markets(center, region.title(), radius=0.08)
                if center
                else {"places": [], "source": "osm", "message": "Wilayah tidak ditemukan."}
            )
    except MapLimited as exc:
        return {
            **fallback,
            "message": "Layanan peta sedang sibuk. Menampilkan data kurasi.",
            "retry_after": exc.retry_after,
        }
    except MapUnavailable:
        return {**fallback, "message": "Layanan peta tidak tersedia. Menampilkan data kurasi."}
    if not result["places"] and fallback["places"]:
        return {**fallback, "message": "Hasil daring kosong. Menampilkan data kurasi."}
    MapLookupCache.objects.update_or_create(
        pk=key, defaults={"payload": result, "expires_at": timezone.now() + timedelta(days=7)}
    )
    old = list(
        MapLookupCache.objects.filter(
            expires_at__lt=timezone.now() - timedelta(days=7)
        ).values_list("pk", flat=True)[:50]
    )
    MapLookupCache.objects.filter(pk__in=old).delete()
    return result
