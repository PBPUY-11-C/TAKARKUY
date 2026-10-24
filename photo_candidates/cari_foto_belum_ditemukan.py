"""Cari kandidat gambar Commons hanya untuk resep berstatus Belum ditemukan."""

from __future__ import annotations

import csv
import html
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "kandidat_foto.csv"
HTML_PATH = ROOT / "kandidat_foto.html"
API = "https://commons.wikimedia.org/w/api.php"
FIELDS = [
    "kode", "nama", "query", "sumber", "halaman_sumber",
    "url_gambar_langsung", "pembuat", "lisensi", "url_lisensi",
    "atribusi", "judul_file", "skor_kata", "status", "catatan",
]
STOPWORDS = {
    "dan", "dengan", "untuk", "tanpa", "ala", "resep", "rumahan",
    "masakan", "khas", "serta", "plus", "nasi", "tumis", "goreng",
    "masak", "pedas", "manis", "tanpa",
}
SYNONYMS = {
    "ayam": "chicken", "ikan": "fish", "tongkol": "tuna", "patin": "catfish",
    "kembung": "mackerel", "bandeng": "milkfish", "dori": "dory",
    "tahu": "tofu", "tempe": "tempeh", "goreng": "fried", "bakar": "grilled",
    "panggang": "grilled", "gulai": "curry", "balado": "sambal",
    "telur": "egg", "kentang": "potato", "buncis": "green beans",
    "bayam": "spinach", "wortel": "carrot", "padeh": "pedas",
    "tanpa": "boneless", "tulang": "bone", "kacang": "peanut",
}
PROTEIN_TERMS = {
    "ayam": {"ayam", "chicken"}, "ikan": {"ikan", "fish"},
    "tongkol": {"tongkol", "tuna", "skipjack"}, "patin": {"patin", "catfish"},
    "kembung": {"kembung", "mackerel"}, "bandeng": {"bandeng", "milkfish"},
    "dori": {"dori", "dory"}, "tahu": {"tahu", "tofu"},
    "tempe": {"tempe", "tempeh"}, "telur": {"telur", "egg"},
}


def normalized_url(url: str) -> str:
    parts = urlsplit(url or "")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, "", ""))


def tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {word for word in words if len(word) > 1 and word not in STOPWORDS}


def search_commons(query: str) -> list[dict]:
    params = {
        "action": "query", "format": "json", "formatversion": "2",
        "generator": "search", "gsrnamespace": "6", "gsrlimit": "12",
        "gsrsearch": query, "prop": "imageinfo", "iiprop": "url|extmetadata",
        "iiurlwidth": "600", "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl|Attribution",
    }
    request = Request(
        f"{API}?{urlencode(params)}",
        headers={"User-Agent": "TakarkuyRecipePhotoFinder/1.0 (recipe image candidate research)"},
    )
    for attempt in range(4):
        try:
            with urlopen(request, timeout=30) as response:
                data = json.load(response)
            return data.get("query", {}).get("pages", [])
        except HTTPError as exc:
            if exc.code != 429 or attempt == 3:
                raise
            retry_after = exc.headers.get("Retry-After", "30")
            try:
                delay = max(15, min(120, int(retry_after)))
            except ValueError:
                delay = 30 * (attempt + 1)
            print(f"Wikimedia meminta jeda {delay} detik; mencoba lagi otomatis.", flush=True)
            time.sleep(delay)
    return []


def metadata_value(metadata: dict, key: str) -> str:
    value = metadata.get(key, {})
    return str(value.get("value", "")) if isinstance(value, dict) else ""


def make_queries(recipe: dict) -> list[str]:
    name = recipe.get("query") or recipe.get("nama", "")
    raw_words = [word for word in re.findall(r"[a-z0-9]+", name.lower()) if len(word) > 1]
    core = [word for word in raw_words if word not in STOPWORDS]
    core = list(dict.fromkeys(core))
    queries = [name]
    if len(core) >= 3:
        queries.append(" ".join(core[:3]))
    elif core:
        queries.append(" ".join(core))
    translated = list(dict.fromkeys(
        SYNONYMS.get(word, word) for word in raw_words if word not in {"dan", "dengan", "untuk", "tanpa", "ala", "plus"}
    ))
    if translated:
        queries.append(" ".join(translated))
    return list(dict.fromkeys(q.strip() for q in queries if q.strip()))


def find_candidates(recipe: dict, existing_urls: set[str]) -> list[dict]:
    raw_words = re.findall(r"[a-z0-9]+", (recipe.get("query") or recipe.get("nama", "")).lower())
    query_words = [word for word in raw_words if len(word) > 1 and word not in STOPWORDS]
    found: dict[str, dict] = {}
    for query in make_queries(recipe):
        try:
            pages = search_commons(query)
        except Exception as exc:
            if isinstance(exc, HTTPError) and exc.code == 429:
                raise RuntimeError(
                    "Wikimedia Commons membatasi permintaan (HTTP 429). "
                    "Progres yang sudah selesai disimpan; resep berikutnya belum diproses."
                ) from exc
            print(f"  Pencarian gagal ({query}): {exc}", file=sys.stderr)
            continue
        for page in pages:
            imageinfo = (page.get("imageinfo") or [{}])[0]
            direct_url = imageinfo.get("url", "")
            key = normalized_url(direct_url)
            if not direct_url or key in existing_urls or key in found:
                continue
            title = page.get("title", "")
            title_words = tokens(title)
            normalized_title = title.lower()
            recipe_words = set(raw_words)
            anchor_terms = set().union(*(PROTEIN_TERMS[word] for word in recipe_words if word in PROTEIN_TERMS))
            if anchor_terms and not (anchor_terms & title_words):
                continue
            if "tanpa" in recipe_words and any(term in title_words for term in {"santan", "coconut", "lemak"}):
                continue
            if "bumbu" in normalized_title and "bumbu" not in recipe_words:
                continue
            if "mie" in title_words and "mie" not in recipe_words:
                continue
            if "hoisin" in recipe_words and any(term in title_words for term in {"satay", "sate", "peanut"}):
                continue
            matched = sum(
                1 for word in query_words
                if word in title_words or any(alias in title_words for alias in SYNONYMS.get(word, "").split())
            )
            score = matched / max(1, len(query_words))
            # Penalti judul generik dan hasil yang tidak menyebut bahan utama.
            if matched < 2 or score < 0.50:
                continue
            metadata = imageinfo.get("extmetadata", {})
            landing = "https://commons.wikimedia.org/wiki/" + quote(title.replace(" ", "_"), safe=":()_.,-'")
            creator = metadata_value(metadata, "Artist")
            license_name = metadata_value(metadata, "LicenseShortName")
            license_url = metadata_value(metadata, "LicenseUrl")
            if not license_name or not license_url:
                continue
            attribution = metadata_value(metadata, "Attribution")
            thumbnail = imageinfo.get("thumburl") or direct_url
            found[key] = {
                "kode": recipe["kode"], "nama": recipe["nama"], "query": recipe.get("query", ""),
                "sumber": "Wikimedia Commons", "halaman_sumber": landing,
                "url_gambar_langsung": direct_url, "pembuat": creator,
                "lisensi": license_name, "url_lisensi": license_url,
                "atribusi": attribution, "judul_file": title,
                "skor_kata": f"{score:.2f}", "status": "KANDIDAT (perlu cek visual)",
                "catatan": "Periksa kecocokan visual dan atribusi sebelum dipakai.",
                "_thumbnail": thumbnail,
            }
        # Query alternatif hanya diperlukan jika query utama belum menghasilkan kandidat.
        if found:
            break
        time.sleep(3)
    ranked = sorted(found.values(), key=lambda item: (-float(item["skor_kata"]), item["judul_file"].lower()))
    return ranked[:5]


def render_html(rows: list[dict]) -> None:
    candidates = [row for row in rows if row.get("url_gambar_langsung")]
    cards = []
    for row in candidates:
        thumb = row.get("_thumbnail") or row.get("url_gambar_langsung", "")
        cards.append(
            "<tr>"
            f"<td>{html.escape(row.get('kode', ''))}<br>{html.escape(row.get('nama', ''))}</td>"
            f"<td><img src=\"{html.escape(thumb, quote=True)}\" width=200 loading=lazy></td>"
            f"<td>{html.escape(row.get('sumber', ''))}<br>skor {html.escape(row.get('skor_kata', ''))}<br>{html.escape(row.get('judul_file', ''))}</td>"
            f"<td>{html.escape(row.get('pembuat', ''))}<br>{html.escape(row.get('lisensi', ''))}</td>"
            f"<td><a href=\"{html.escape(row.get('halaman_sumber', ''), quote=True)}\">halaman</a></td>"
            "</tr>"
        )
    document = (
        "<!doctype html><html lang=\"id\"><meta charset=\"utf-8\"><title>Kandidat foto resep</title>"
        "<style>body{font:14px system-ui;margin:24px}table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:8px;vertical-align:top}img{object-fit:contain;max-height:160px}</style>"
        f"<h1>Kandidat foto ({len(candidates)})</h1><table><thead><tr><th>Resep</th><th>Foto</th><th>Sumber</th><th>Pembuat/lisensi</th><th>Halaman</th></tr></thead><tbody>{''.join(cards)}</tbody></table></html>"
    )
    HTML_PATH.write_text(document, encoding="utf-8")


def save_outputs(rows: list[dict]) -> None:
    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as target:
        writer = csv.DictWriter(target, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    render_html(rows)


def main() -> None:
    with CSV_PATH.open("r", newline="", encoding="utf-8-sig") as source:
        rows = list(csv.DictReader(source))
    known_urls = {normalized_url(row.get("url_gambar_langsung", "")) for row in rows if row.get("url_gambar_langsung")}
    # Setiap resep unik yang belum punya kandidat diproses sekali.
    missing = {}
    for row in rows:
        if row.get("status", "").strip().lower() == "belum ditemukan":
            missing.setdefault(row.get("kode", ""), row)
    print(f"Resep berstatus Belum ditemukan: {len(missing)}")
    if not missing:
        print("Tidak ada resep yang perlu dicari.")
        render_html(rows)
        return

    added = 0
    interrupted_by_limit = False
    for index, (code, recipe) in enumerate(missing.items(), 1):
        print(f"[{index}/{len(missing)}] {recipe.get('nama', code)}", flush=True)
        try:
            candidates = find_candidates(recipe, known_urls)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr, flush=True)
            interrupted_by_limit = True
            break
        if candidates:
            rows = [row for row in rows if row.get("kode") != code]
            for candidate in candidates[:3]:
                candidate.pop("_thumbnail", None)
                rows.append(candidate)
                known_urls.add(normalized_url(candidate["url_gambar_langsung"]))
            added += min(3, len(candidates))
            print(f"  Kandidat baru: {min(3, len(candidates))}", flush=True)
        else:
            print("  Belum ada kecocokan judul yang cukup", flush=True)
        # Simpan progres tiap resep supaya hasil sebelumnya tidak hilang jika dibatasi.
        save_outputs(rows)
    save_outputs(rows)
    remaining = sum(row.get("status", "").strip().lower() == "belum ditemukan" for row in rows)
    print(f"Selesai. Kandidat baru: {added}; resep masih Belum ditemukan: {remaining}.")
    if interrupted_by_limit:
        print("Jalankan lagi nanti untuk melanjutkan; kandidat yang sudah tercatat tidak akan ditambahkan ulang.")
    print(f"CSV: {CSV_PATH}")
    print(f"Galeri: {HTML_PATH}")


if __name__ == "__main__":
    main()
