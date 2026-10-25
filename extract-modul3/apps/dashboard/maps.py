"""Curated fallback + optional public-region OSM lookup, never user GPS."""

import hashlib
import json
import math
import re
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import MapLookupCache, MapProviderGate, MapQuota


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


def curated(region, kind):
    data = read_places()
    query = normalized_region(region)
    places = [
        place
        for place in data["places"]
        if (query in place["region"].casefold() or query in place["address"].casefold())
        and (kind == "all" or place["kind"] == kind)
    ]
    return {
        "places": places,
        "source": "curated",
        "reviewed_on": data["reviewed_on"],
        "message": "" if places else "Data belum tersedia di wilayah ini.",
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


def _http(provider, url, body=""):
    identity = settings.MAP_USER_AGENT
    if not identity or "TAKARKUY" not in identity or not re.search(r"https://|@", identity):
        raise MapUnavailable("Identitas aplikasi peta belum diatur.")
    url = endpoint(url)
    key = hashlib.sha256(provider.encode()).hexdigest()
    now, token = timezone.now(), uuid4()
    with transaction.atomic():
        gate, _ = MapProviderGate.objects.get_or_create(
            key=key, defaults={"next_at": now, "lease_until": now}
        )
        gate = MapProviderGate.objects.select_for_update().get(pk=gate.pk)
        wait = max((gate.next_at - now).total_seconds(), (gate.lease_until - now).total_seconds())
        if wait > 0:
            raise MapLimited(wait)
        gate.next_at = now + timedelta(seconds=1.1)
        gate.lease_until, gate.lease = now + timedelta(seconds=12), token
        gate.save()
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
            [sys.executable, "-m", "apps.dashboard.map_transport"],
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
    # Same geocoding query across all filters/accounts must share one cache.
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


def osm_places(region, kind):
    center = geocode_region(region)
    if center is None:
        return {"places": [], "source": "osm", "message": "Wilayah tidak ditemukan."}
    lat, lon = center
    bbox = (
        f"{max(-11, lat - 0.08)},{max(95, lon - 0.08)},{min(6, lat + 0.08)},{min(141, lon + 0.08)}"
    )
    queries = []
    if kind in {"all", "market"}:
        queries.append(f'nwr["amenity"="marketplace"]({bbox});')
    if kind in {"all", "waste_bank"}:
        queries.append(f'nwr["name"~"bank sampah",i]({bbox});')
    result = _http(
        "overpass",
        endpoint(settings.MAP_OVERPASS_URL),
        urlencode({"data": "[out:json][timeout:5];(" + "".join(queries) + ");out center 30;"}),
    )
    if not isinstance(result, dict) or not isinstance(result.get("elements"), list):
        raise MapUnavailable("Hasil peta tidak valid.")
    if result.get("remark"):
        raise MapUnavailable("Pencarian peta belum lengkap.")
    places = []
    for element in result["elements"][:30]:
        if not isinstance(element, dict):
            continue
        tags = element.get("tags", {})
        if not isinstance(tags, dict) or not isinstance(tags.get("name"), str):
            continue
        position = element.get("center", element)
        point = (
            coordinates(position.get("lat"), position.get("lon"))
            if isinstance(position, dict)
            else None
        )
        name = tags["name"][:150]
        group = "waste_bank" if "bank sampah" in name.casefold() else "market"
        if point is None or (group == "market" and tags.get("amenity") != "marketplace"):
            continue
        if kind != "all" and kind != group:
            continue
        if (
            element.get("type") not in {"node", "way", "relation"}
            or type(element.get("id")) is not int
            or element["id"] < 1
        ):
            continue
        places.append(
            {
                "id": f"osm-{element['type']}-{element['id']}",
                "name": name,
                "kind": group,
                "region": region,
                "address": str(tags.get("addr:street", ""))[:200],
                "lat": point[0],
                "lon": point[1],
                "source_url": f"https://www.openstreetmap.org/{element['type']}/{element['id']}",
                "note": "Data komunitas OSM; konfirmasi lokasi dan layanan sebelum datang.",
            }
        )
    return {
        "places": places,
        "center": list(center),
        "source": "osm",
        "message": "" if places else "Data belum tersedia di wilayah ini.",
    }


def lookup_places(user, data):
    if set(data) - {"region", "kind", "online"}:
        raise ValueError("Kirim wilayah saja; koordinat pribadi tidak diterima.")
    region, kind, online = (
        normalized_region(data.get("region")),
        data.get("kind", "all"),
        data.get("online", False),
    )
    if (
        not isinstance(kind, str)
        or kind not in {"all", "market", "waste_bank"}
        or type(online) is not bool
    ):
        raise ValueError("Pilihan pencarian tidak valid.")
    fallback = curated(region, kind)
    if not online:
        return fallback
    # Public Nominatim is opt-in by the operator, not an automatic generic
    # geocoder. No autocomplete, background lookup or coordinate requests.
    if not settings.MAP_LOOKUP_ENABLED:
        return {
            **fallback,
            "message": "Pencarian daring belum diaktifkan. Menampilkan data kurasi.",
        }
    # Account quota stays outside the provider fallback: quota exhaustion must
    # remain 429, but offline/disabled lookups never spend online quota.
    reserve_map(user)
    key = hashlib.sha256(
        json.dumps(
            ["maps-v1", region, kind, settings.MAP_GEOCODER_URL, settings.MAP_OVERPASS_URL]
        ).encode()
    ).hexdigest()
    cached = MapLookupCache.objects.filter(pk=key, expires_at__gt=timezone.now()).first()
    if cached:
        return {**cached.payload, "cached": True}
    try:
        result = osm_places(region, kind)
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
