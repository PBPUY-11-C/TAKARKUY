"""Cari kandidat foto berlisensi terbuka untuk resep Recipe Book tanpa foto."""

from __future__ import annotations

import csv
import argparse
import html
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "kandidat_foto.csv"
HTML_PATH = ROOT / "kandidat_foto.html"
REPO = ROOT.parent
OPENVERSE_API = "https://api.openverse.org/v1/images/"
RECIPE_CSV = REPO / "data" / "processed" / "recipes.csv"
MAPPING_CSV = REPO / "data" / "mapping" / "recipe_image_mapping.csv"
SEARCH_VERSION = "openverse-match-v5"
# Use the same curated names and spelling rules as the recipe catalog builder.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from data.recipe_names import DEACTIVATE, EXCLUDE, load_overrides, standard_name

FIELDS = [
    "kode", "nama", "query", "sumber", "halaman_sumber",
    "url_gambar_langsung", "pembuat", "lisensi", "url_lisensi",
    "atribusi", "judul_file", "skor_kata", "status", "catatan",
]
STOPWORDS = {
    "dan", "dengan", "untuk", "tanpa", "ala", "resep", "rumahan",
    "masakan", "khas", "serta", "plus", "nasi", "tumis", "goreng",
    "masak", "pedas", "manis", "tanpa", "orak", "arik", "kukus",
    "panggang", "bakar", "rebus", "ceplok", "dadar", "suwir", "oseng",
    "liwet", "goreng", "bumbu",
}
SYNONYMS = {
    "ayam": "chicken", "ikan": "fish", "tongkol": "tuna", "patin": "catfish",
    "kembung": "mackerel", "bandeng": "milkfish", "dori": "dory",
    "lele": "catfish", "mujair": "tilapia", "tuna": "tuna",
    "teri": "anchovy", "mas": "carp", "tenggiri": "spanish mackerel",
    "cakalang": "skipjack tuna", "gurame": "giant gourami", "nila": "tilapia",
    "bawal": "pomfret", "sarden": "sardine", "cumi": "squid", "kerang": "clam",
    "kambing": "goat", "bebek": "duck", "paru": "beef lung", "kikil": "beef tendon",
    "puyuh": "quail",
    "tahu": "tofu", "tempe": "tempeh", "goreng": "fried", "bakar": "grilled",
    "panggang": "grilled", "gulai": "curry", "balado": "sambal",
    "telur": "egg", "kentang": "potato", "buncis": "green beans",
    "bayam": "spinach", "wortel": "carrot", "padeh": "pedas",
    "tanpa": "boneless", "tulang": "bone", "kacang": "peanut",
    "sayur": "vegetable", "jagung": "corn", "sapi": "beef",
    "daging": "meat", "udang": "shrimp", "kangkung": "water spinach",
    "pakcoy": "bok choy", "sawi": "mustard greens", "kubis": "cabbage",
    "kol": "cabbage", "tomat": "tomato", "ubi": "sweet potato",
    "singkong": "cassava", "semur": "stew", "sup": "soup",
    "kukus": "steamed", "nasi": "rice", "tumis": "stir fry",
    "mi": "noodles", "mie": "noodles", "kecap": "soy sauce", "saus": "sauce",
    "minyak": "oil", "gula": "sugar",
    "orak": "scrambled", "arik": "scrambled", "buah": "fruit",
    "pisang": "banana", "jeruk": "orange", "melon": "melon",
    "bawang": "onion", "cabai": "chili", "cabe": "chili",
    "santan": "coconut milk", "terong": "eggplant", "petai": "stink bean",
    "jengkol": "djenkol", "tauge": "bean sprouts", "kemangi": "lemon basil",
    "serai": "lemongrass", "kemiri": "candlenut", "lengkuas": "galangal",
    "kencur": "aromatic ginger", "kunyit": "turmeric", "ketumbar": "coriander",
    "terasi": "shrimp paste", "ebi": "dried shrimp", "seledri": "celery",
    "bihun": "rice vermicelli", "soun": "glass noodles", "paprika": "bell pepper",
    "sambal": "chili sauce", "rica": "chili", "pepes": "banana leaf steamed",
    "opor": "coconut curry", "lodeh": "vegetable coconut curry", "soto": "soup",
    "pindang": "fish soup", "suwir": "shredded", "ceplok": "fried egg",
    "dadar": "omelet", "oseng": "stir fry", "liwet": "rice", "bubur": "porridge",
    "pare": "bitter melon", "oyong": "luffa", "rebung": "bamboo shoots",
    "genjer": "water mimosa", "kluwek": "black nut", "kunci": "fingerroot",
    "pandan": "pandan leaves", "asam": "sour", "asem": "sour",
    "rawit": "bird's eye chili", "merah": "red", "putih": "white",
    "hijau": "green", "matah": "raw", "asin": "salted", "segar": "fresh",
}
PHRASE_SYNONYMS = {
    "ikan asin teri": "salted anchovy",
    "ikan asin": "salted fish",
    "ikan tenggiri": "spanish mackerel",
    "ikan kembung": "mackerel",
    "ikan bandeng": "milkfish",
    "ikan mujair": "tilapia",
    "ikan lele": "catfish",
    "ikan tongkol": "skipjack tuna",
    "ikan patin": "catfish",
    "ikan mas": "carp",
    "ikan teri": "anchovy",
    "ikan cakalang": "skipjack tuna",
    "ikan gurame": "giant gourami",
    "ikan nila": "tilapia",
    "ikan bawal": "pomfret",
    "ikan sarden": "sardine",
    "cumi asin": "salted squid",
    "kacang panjang": "long beans",
    "kacang hijau": "mung beans",
    "kacang tanah": "peanuts",
    "bawang merah": "shallots",
    "bawang putih": "garlic",
    "daun bawang": "scallion",
    "daun jeruk": "kaffir lime leaves",
    "daun salam": "indonesian bay leaves",
    "daun singkong": "cassava leaves",
    "daun pepaya": "papaya leaves",
    "daun pandan": "pandan leaves",
    "jantung pisang": "banana blossom",
    "asam jawa": "tamarind",
    "sawi putih": "napa cabbage",
    "ati ampela": "chicken liver gizzard",
    "telur puyuh": "quail eggs",
    "cabe merah keriting": "red curly chili",
    "cabai merah keriting": "red curly chili",
    "cabe rawit merah": "red bird's eye chili",
    "cabai rawit merah": "red bird's eye chili",
    "bawang bombay": "onion",
    "sambal matah": "Balinese raw sambal",
    "ayam suwir": "shredded chicken",
    "ayam rica-rica": "Manado spicy chicken",
    "asam padeh": "spicy sour fish",
    "bumbu kuning": "turmeric spice",
    "gula merah": "brown sugar",
    "ayam kampung": "free range chicken",
    "kecap manis": "sweet soy sauce",
    "saus tiram": "oyster sauce",
    "tepung tapioka": "tapioca starch",
    "tepung panir": "breadcrumbs",
    "labu siam": "chayote",
    "labu kuning": "pumpkin",
}
RECIPE_ANCHORS = {
    "ayam": {"ayam", "chicken"}, "ikan": {"ikan", "fish"},
    "tongkol": {"tongkol", "tuna", "skipjack"}, "patin": {"patin", "catfish"},
    "kembung": {"kembung", "mackerel"}, "bandeng": {"bandeng", "milkfish"},
    "dori": {"dori", "dory"}, "tahu": {"tahu", "tofu"},
    "tempe": {"tempe", "tempeh"}, "telur": {"telur", "egg"},
    "jagung": {"jagung", "corn", "maize"}, "udang": {"udang", "shrimp", "prawn"},
    "sapi": {"sapi", "beef"}, "kentang": {"kentang", "potato"},
    "buncis": {"buncis", "beans", "bean"}, "bayam": {"bayam", "spinach"},
    "wortel": {"wortel", "carrot"}, "kangkung": {"kangkung", "water", "spinach"},
    "pakcoy": {"pakcoy", "bok", "choy"}, "kubis": {"kubis", "cabbage"},
    "tomat": {"tomat", "tomato"}, "ubi": {"ubi", "yam", "sweet", "potato"},
    "singkong": {"singkong", "cassava", "yuca"},
    "pisang": {"pisang", "banana", "plantain"},
    "jeruk": {"jeruk", "orange", "citrus"}, "melon": {"melon"},
    "buah": {"buah", "fruit"}, "bawang": {"bawang", "onion"},
    "cabai": {"cabai", "chili", "chilli"}, "cabe": {"cabe", "chili", "chilli"},
    "lele": {"lele", "catfish"}, "mujair": {"mujair", "tilapia"},
    "tuna": {"tuna"}, "teri": {"teri", "anchovy"}, "mas": {"mas", "carp"},
    "tenggiri": {"tenggiri", "mackerel"}, "terong": {"terong", "eggplant", "aubergine"},
    "petai": {"petai", "stink", "bean"}, "jengkol": {"jengkol", "djenkol"},
    "tauge": {"tauge", "sprout", "sprouts"}, "sawi": {"sawi", "mustard", "greens"},
    "labu": {"labu", "pumpkin", "squash", "chayote"},
    "panjang": {"panjang", "long", "bean", "beans"},
    "cakalang": {"cakalang", "skipjack", "tuna"},
    "gurame": {"gurame", "gourami"}, "nila": {"nila", "tilapia"},
    "bawal": {"bawal", "pomfret"}, "sarden": {"sarden", "sardine"},
    "cumi": {"cumi", "squid"}, "kerang": {"kerang", "clam", "clams"},
    "kambing": {"kambing", "goat"}, "bebek": {"bebek", "duck"},
    "paru": {"paru", "lung"}, "kikil": {"kikil", "tendon"},
    "pare": {"pare", "bitter", "melon"}, "oyong": {"oyong", "luffa"},
    "rebung": {"rebung", "bamboo", "shoots"}, "genjer": {"genjer", "mimosa"},
}


def normalized_url(url: str) -> str:
    parts = urlsplit(url or "")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, "", ""))


def tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {word for word in words if len(word) > 1 and word not in STOPWORDS}


def escape_html(value: object, *, quote: bool = False) -> str:
    """Escape metadata safely; external APIs may explicitly return null values."""
    return html.escape(str(value or ""), quote=quote)


def search_openverse(query: str) -> list[dict]:
    """Search CC/public-domain photos with commercial reuse permissions."""
    params = urlencode({
        "q": query,
        "page_size": 20,
        "license_type": "commercial",
        "mature": "false",
    })
    request = Request(
        f"{OPENVERSE_API}?{params}",
        headers={"User-Agent": "TAKARKUY/1.0 (recipe photo candidate research)"},
    )
    for attempt in range(4):
        try:
            with urlopen(request, timeout=30) as response:
                data = json.load(response)
            return data.get("results", [])
        except HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 3:
                raise
            retry_after = exc.headers.get("Retry-After", "30")
            try:
                delay = max(2, min(120, int(retry_after)))
            except ValueError:
                delay = 5 * (attempt + 1)
            print(f"Openverse meminta jeda {delay} detik; mencoba lagi otomatis.", flush=True)
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
    if core:
        queries.append(" ".join(core))

    # Translate complete Indonesian phrases first (e.g. kacang panjang ->
    # long beans), then translate the remaining ingredient words.
    translated_name = name.casefold()
    for phrase, translation in sorted(PHRASE_SYNONYMS.items(), key=lambda pair: -len(pair[0])):
        translated_name = re.sub(rf"\b{re.escape(phrase)}\b", translation, translated_name)
    translated = []
    for word in re.findall(r"[a-z0-9]+", translated_name):
        if word in STOPWORDS:
            continue
        translated.extend(SYNONYMS.get(word, word).split())
    translated = list(dict.fromkeys(word for word in translated if word not in STOPWORDS))
    if translated:
        queries.append(" ".join(translated))

    anchors = [
        SYNONYMS.get(word, word)
        for word in core
        if word in RECIPE_ANCHORS
    ]
    if anchors:
        anchors = list(dict.fromkeys(anchors))
        queries.append(" ".join(anchors))
        # Single-ingredient searches rescue composites whose image title only
        # names the main ingredient, such as egg, tempeh, or cassava.
        queries.extend(anchors[:2])
    # Keep a small, useful batch: exact Indonesian name first, then ingredient
    # wording and translation. This improves precision without flooding APIs.
    return list(dict.fromkeys(q.strip() for q in queries if q.strip()))[:3]


def find_candidates(recipe: dict, existing_urls: set[str]) -> list[dict]:
    raw_words = re.findall(r"[a-z0-9]+", (recipe.get("query") or recipe.get("nama", "")).lower())
    query_words = [word for word in raw_words if len(word) > 1 and word not in STOPWORDS]
    found: dict[str, dict] = {}
    blocked_visual_terms = {
        "menu", "chalkboard", "signboard", "restaurant sign", "packaging",
        "poster", "logo", "clipart", "illustration", "recipe book", "screenshot",
    }
    for query in make_queries(recipe):
        try:
            results = search_openverse(query)
        except Exception as exc:
            raise RuntimeError(f"Pencarian Openverse gagal ({query}): {exc}") from exc
        for result in results:
            direct_url = result.get("url", "")
            key = normalized_url(direct_url)
            if not direct_url or key in existing_urls or key in found:
                continue
            if urlsplit(direct_url).scheme != "https":
                continue
            category = str(result.get("category") or "").lower()
            filetype = str(result.get("filetype") or "").lower()
            if category and category not in {"photograph", ""}:
                continue
            if filetype == "svg":
                continue
            title = str(result.get("title") or "")
            description = str(result.get("description") or "")
            raw_tags = result.get("tags") or []
            if isinstance(raw_tags, str):
                raw_tags = [raw_tags]
            tag_names = [
                str(tag.get("name") or "") if isinstance(tag, dict) else str(tag or "")
                for tag in raw_tags
            ]
            title_words = tokens(title)
            description_words = tokens(description)
            tag_words = tokens(" ".join(tag_names))
            metadata_words = title_words | description_words | tag_words
            normalized_title = " ".join([title, description, " ".join(tag_names)]).casefold()
            if any(term in normalized_title for term in blocked_visual_terms):
                continue
            recipe_words = set(raw_words)
            anchor_terms = set().union(*(RECIPE_ANCHORS[word] for word in recipe_words if word in RECIPE_ANCHORS))
            matched_anchors = anchor_terms & metadata_words
            title_anchor_match = anchor_terms & title_words
            if anchor_terms and not matched_anchors:
                continue
            if "tanpa" in recipe_words and any(term in metadata_words for term in {"santan", "coconut", "lemak"}):
                continue
            if "bumbu" in metadata_words and "bumbu" not in recipe_words:
                continue
            if "mie" in metadata_words and "mie" not in recipe_words:
                continue
            if "hoisin" in recipe_words and any(term in metadata_words for term in {"satay", "sate", "peanut"}):
                continue
            def word_matches(word: str, word_set: set[str]) -> bool:
                aliases = {word, *SYNONYMS.get(word, "").split()}
                return bool(aliases & word_set)

            title_matches = sum(word_matches(word, title_words) for word in dict.fromkeys(query_words))
            description_matches = sum(word_matches(word, description_words) for word in dict.fromkeys(query_words))
            tag_matches = sum(word_matches(word, tag_words) for word in dict.fromkeys(query_words))
            denominator = max(1, len(set(query_words)))
            title_coverage = title_matches / denominator
            # The title carries most of the relevance signal. Description and
            # tags can help rank, but cannot rescue a title with no dish match.
            score = (0.80 * title_matches + 0.12 * description_matches + 0.08 * tag_matches) / denominator
            minimum_title_matches = 1 if len(set(query_words)) == 1 else 2
            if title_matches < minimum_title_matches or title_coverage < 0.45:
                continue
            if anchor_terms and not title_anchor_match:
                continue
            license_code = str(result.get("license", "")).lower()
            if license_code not in {"cc0", "pdm", "by", "by-sa"}:
                continue
            license_name = license_code.upper() if license_code in {"cc0", "pdm"} else f"CC {license_code.upper()}"
            license_version = result.get("license_version") or ""
            if license_version:
                license_name = f"{license_name} {license_version}"
            license_url = result.get("license_url") or ""
            landing = result.get("foreign_landing_url") or result.get("detail_url") or ""
            if not license_url or not landing:
                continue
            creator = result.get("creator") or ""
            provider = result.get("source") or "Openverse"
            attribution = result.get("attribution") or ""
            thumbnail = result.get("thumbnail") or direct_url
            found[key] = {
                "kode": recipe["kode"], "nama": recipe["nama"], "query": recipe.get("query", ""),
                "sumber": f"Openverse/{provider}", "halaman_sumber": landing,
                "url_gambar_langsung": direct_url, "pembuat": creator,
                "lisensi": license_name, "url_lisensi": license_url,
                "atribusi": attribution, "judul_file": title,
                "skor_kata": f"{score:.2f}", "status": "KANDIDAT PRIORITAS (cek visual)",
                "catatan": (
                    f"{SEARCH_VERSION}: satu kandidat terbaik; kecocokan judul {title_coverage:.0%}. "
                    "Skor teks bukan verifikasi visual; pastikan foto benar-benar hidangan ini dan lisensinya sesuai."
                ),
                "_thumbnail": thumbnail,
                "_title_coverage": title_coverage,
            }
        time.sleep(0.5)
    ranked = sorted(
        found.values(),
        key=lambda item: (-item["_title_coverage"], -float(item["skor_kata"]), item["judul_file"].casefold()),
    )
    return ranked[:1]


def render_html(rows: list[dict]) -> None:
    candidates = [row for row in rows if row.get("url_gambar_langsung")]
    cards = []
    for row in candidates:
        thumb = row.get("_thumbnail") or row.get("url_gambar_langsung", "")
        review_key = f"{row.get('kode', '')}|{normalized_url(row.get('url_gambar_langsung', ''))}"
        cards.append(
            f"<tr data-review-key=\"{escape_html(review_key, quote=True)}\" data-recipe-code=\"{escape_html(row.get('kode'), quote=True)}\" data-image-url=\"{escape_html(row.get('url_gambar_langsung'), quote=True)}\" data-source-url=\"{escape_html(row.get('halaman_sumber'), quote=True)}\" data-creator=\"{escape_html(row.get('pembuat'), quote=True)}\" data-license=\"{escape_html(row.get('lisensi'), quote=True)}\" data-license-url=\"{escape_html(row.get('url_lisensi'), quote=True)}\" data-file-title=\"{escape_html(row.get('judul_file'), quote=True)}\">"
            f"<td>{escape_html(row.get('kode'))}<br>{escape_html(row.get('nama'))}</td>"
            f"<td><img src=\"{escape_html(thumb, quote=True)}\" width=200 loading=lazy></td>"
            f"<td>{escape_html(row.get('sumber'))}<br>skor {escape_html(row.get('skor_kata'))}<br>{escape_html(row.get('judul_file'))}</td>"
            f"<td>{escape_html(row.get('pembuat'))}<br>"
            f"<a href=\"{escape_html(row.get('url_lisensi'), quote=True)}\">{escape_html(row.get('lisensi'))}</a></td>"
            f"<td><a href=\"{escape_html(row.get('halaman_sumber'), quote=True)}\" target=\"_blank\" rel=\"noreferrer\">halaman sumber</a></td>"
            "<td class=\"review\"><button type=\"button\" data-choice=\"approved\">Pilih foto</button> "
            "<button type=\"button\" data-choice=\"rejected\">Tolak</button> "
            "<button type=\"button\" data-choice=\"pending\">Reset</button>"
            "<div class=\"state\">Belum ditinjau</div></td>"
            "</tr>"
        )
    document = (
        "<!doctype html><html lang=\"id\"><meta charset=\"utf-8\"><title>Kandidat foto resep</title>"
        "<style>body{font:14px system-ui;margin:24px;color:#172033}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:8px;vertical-align:top}img{object-fit:contain;max-height:180px;max-width:260px}.toolbar{position:sticky;top:0;background:#fff;padding:12px;border:1px solid #bbb;z-index:2}.review button{margin:3px;padding:7px;cursor:pointer}.approved{background:#e5f6eb}.rejected{background:#fce8e8}.state{margin-top:6px;font-weight:600}.hint{color:#555}</style>"
        f"<h1>Kandidat foto ({len(candidates)})</h1>"
        "<div class=\"toolbar\"><button id=\"export\" type=\"button\">Unduh pilihan (CSV pemetaan)</button> "
        "<button id=\"clear\" type=\"button\">Hapus semua pilihan</button> "
        "<label>Filter: <select id=\"filter\"><option value=\"all\">Semua</option><option value=\"pending\">Belum ditinjau</option><option value=\"approved\">Dipilih</option><option value=\"rejected\">Ditolak</option></select></label> "
        "<span id=\"counts\"></span><p class=\"hint\">Pilihan tersimpan di browser ini. Pilih foto yang benar-benar menampilkan hidangan; klik halaman sumber untuk memeriksa konteks dan lisensi.</p></div>"
        f"<table><thead><tr><th>Resep</th><th>Foto</th><th>Sumber/kecocokan</th><th>Pembuat/lisensi</th><th>Halaman</th><th>Keputusan</th></tr></thead><tbody>{''.join(cards)}</tbody></table>"
        """<script>
const STORAGE_KEY='takarkuy-photo-review-v1';
const rows=[...document.querySelectorAll('tbody tr[data-review-key]')];
let choices={};
try{choices=JSON.parse(localStorage.getItem(STORAGE_KEY)||'{}')}catch{choices={}}
function update(){let counts={pending:0,approved:0,rejected:0};for(const row of rows){const key=row.dataset.reviewKey;const state=choices[key]||'pending';counts[state]++;row.classList.toggle('approved',state==='approved');row.classList.toggle('rejected',state==='rejected');row.querySelector('.state').textContent=state==='approved'?'Dipilih':state==='rejected'?'Ditolak':'Belum ditinjau';const filter=document.querySelector('#filter').value;row.hidden=filter!=='all'&&filter!==state;}document.querySelector('#counts').textContent=`${counts.approved} dipilih · ${counts.rejected} ditolak · ${counts.pending} belum ditinjau`;localStorage.setItem(STORAGE_KEY,JSON.stringify(choices));}
for(const row of rows){row.querySelectorAll('button[data-choice]').forEach(button=>button.addEventListener('click',()=>{const state=button.dataset.choice;if(state==='pending')delete choices[row.dataset.reviewKey];else choices[row.dataset.reviewKey]=state;update()}))}
document.querySelector('#filter').addEventListener('change',update);
document.querySelector('#clear').addEventListener('click',()=>{if(confirm('Hapus semua keputusan foto yang tersimpan di browser ini?')){choices={};update()}});
document.querySelector('#export').addEventListener('click',()=>{const selected=rows.filter(row=>choices[row.dataset.reviewKey]==='approved');if(!selected.length){alert('Belum ada foto yang dipilih.');return}const countsByRecipe={};for(const row of selected){const code=row.dataset.recipeCode;countsByRecipe[code]=(countsByRecipe[code]||0)+1}const duplicates=Object.keys(countsByRecipe).filter(code=>countsByRecipe[code]>1);if(duplicates.length){alert('Pilih tepat satu foto per resep sebelum mengunduh. Resep dengan pilihan ganda: '+duplicates.join(', '));return}const fields=['recipe_code','image_url','source_url','creator','license_name','license_url','file_title'];const csvCell=value=>'"'+String(value||'').replaceAll('"','""')+'"';const data=[fields.join(','),...selected.map(row=>[row.dataset.recipeCode,row.dataset.imageUrl,row.dataset.sourceUrl,row.dataset.creator,row.dataset.license,row.dataset.licenseUrl,row.dataset.fileTitle].map(csvCell).join(','))].join(String.fromCharCode(13,10));const link=document.createElement('a');link.href=URL.createObjectURL(new Blob([String.fromCharCode(65279)+data],{type:'text/csv;charset=utf-8'}));link.download='foto_resep_dipilih.csv';link.click();URL.revokeObjectURL(link.href)});
update();
</script></html>"""
    )
    HTML_PATH.write_text(document, encoding="utf-8")


def save_outputs(rows: list[dict]) -> None:
    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as target:
        writer = csv.DictWriter(target, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    render_html(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cari foto kandidat dari Openverse untuk resep tanpa foto.")
    parser.add_argument("--limit", type=int, default=0, help="Batas jumlah resep per sesi; 0 memproses semua.")
    parser.add_argument("--delay", type=float, default=0.75, help="Jeda antarresep dalam detik.")
    parser.add_argument(
        "--source",
        choices=("all", "themealdb"),
        default="all",
        help="Batasi pencarian ke resep yang sumber katalognya TheMealDB.",
    )
    parser.add_argument("--retry-unfound", action="store_true", help="Cari ulang resep yang sebelumnya tidak mendapat kandidat.")
    args = parser.parse_args()

    with CSV_PATH.open("r", newline="", encoding="utf-8-sig") as source:
        rows = list(csv.DictReader(source))
    overrides = load_overrides(REPO / "data" / "mapping" / "recipe_name_overrides.csv")
    with RECIPE_CSV.open("r", newline="", encoding="utf-8-sig") as source:
        recipes = []
        for item in csv.DictReader(source):
            if item.get("is_active") != "true" or item.get("is_plannable") != "true":
                continue
            if args.source == "themealdb" and not item.get("source", "").startswith("TheMealDB API"):
                continue
            name = item["name"]
            # Match build_final.py: the manually curated TheMealDB display name
            # wins; other recipes use override names followed by spelling rules.
            if item.get("source") != "TheMealDB API; kurasi TAKARKUY":
                override_name, _reason = overrides.get(item["recipe_code"], ("", ""))
                if override_name and override_name not in {EXCLUDE, DEACTIVATE}:
                    name = override_name
                name = standard_name(name)
            recipes.append({"kode": item["recipe_code"], "nama": name, "query": name})
    with MAPPING_CSV.open("r", newline="", encoding="utf-8-sig") as source:
        mapped_codes = {item["recipe_code"] for item in csv.DictReader(source) if item.get("image_url")}
    known_urls = {normalized_url(row.get("url_gambar_langsung", "")) for row in rows if row.get("url_gambar_langsung")}
    # Search all recipes used by the planner that do not yet have a mapped photo.
    existing_openverse = set()
    previously_unfound = set()
    for row in rows:
        if row.get("sumber", "").startswith("Openverse/"):
            existing_openverse.add(row.get("kode", ""))
        if (
            row.get("status", "").strip().lower() == "belum ditemukan"
            and SEARCH_VERSION in row.get("catatan", "").lower()
        ):
            previously_unfound.add(row.get("kode", ""))
    missing = {
        item["kode"]: item for item in recipes
        if item["kode"] not in mapped_codes and item["kode"] not in existing_openverse
        and (args.retry_unfound or item["kode"] not in previously_unfound)
    }
    if args.limit > 0:
        missing = dict(list(missing.items())[:args.limit])
    print(f"Resep tanpa foto terpetakan yang akan dicari: {len(missing)}")
    if not missing:
        print("Semua resep sudah memiliki kandidat Openverse atau foto terpetakan.")
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
            rows = [
                row for row in rows
                if not (
                    row.get("kode") == code
                    and row.get("status", "").strip().lower() == "belum ditemukan"
                )
            ]
            for candidate in candidates[:1]:
                candidate.pop("_thumbnail", None)
                candidate.pop("_title_coverage", None)
                rows.append(candidate)
                known_urls.add(normalized_url(candidate["url_gambar_langsung"]))
            added += 1
            print("  Satu kandidat prioritas baru (perlu cek visual).", flush=True)
        else:
            print("  Belum ada kecocokan judul yang cukup", flush=True)
            placeholder = next((
                row for row in rows
                if row.get("kode") == code
                and row.get("status", "").strip().lower() == "belum ditemukan"
            ), None)
            if placeholder:
                placeholder["nama"] = recipe["nama"]
                placeholder["query"] = recipe["query"]
                placeholder["catatan"] = (
                    f"{SEARCH_VERSION}: Openverse sudah dicari; belum ada kandidat dengan "
                    "kecocokan bahan yang cukup."
                )
            elif not any(row.get("kode") == code and row.get("url_gambar_langsung") for row in rows):
                rows.append({
                    "kode": code, "nama": recipe["nama"], "query": recipe["query"],
                    "status": "Belum ditemukan",
                    "catatan": (
                        f"{SEARCH_VERSION}: Openverse sudah dicari; belum ada kandidat dengan "
                        "kecocokan bahan yang cukup."
                    ),
                })
        # Simpan progres tiap resep supaya hasil sebelumnya tidak hilang jika dibatasi.
        save_outputs(rows)
        time.sleep(max(0, args.delay))
    save_outputs(rows)
    remaining = sum(row.get("status", "").strip().lower() == "belum ditemukan" for row in rows)
    print(f"Selesai. Kandidat baru: {added}; resep masih Belum ditemukan: {remaining}.")
    if interrupted_by_limit:
        print("Jalankan lagi nanti untuk melanjutkan; kandidat yang sudah tercatat tidak akan ditambahkan ulang.")
    print(f"CSV: {CSV_PATH}")
    print(f"Galeri: {HTML_PATH}")


if __name__ == "__main__":
    main()
