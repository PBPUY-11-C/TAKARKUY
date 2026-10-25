"""Clear, standard recipe names shown to users.

Curated renames, exclusions and deactivations live in
mapping/recipe_name_overrides.csv; the
rules below only normalize spelling, casing and source noise such as numbering.
"""

import csv
import re
import unicodedata
from pathlib import Path

EXCLUDE = "exclude"
# Keeps the recipe row and code (saved plans still resolve) but hides it from
# the app with is_active=false. Usable for every source, unlike EXCLUDE.
DEACTIVATE = "nonaktif"
# Standard Indonesian spelling for words that sources write informally.
SPELLING = {
    "telor": "telur",
    "cabe": "cabai",
    "ijo": "hijau",
    "saos": "saus",
    "sop": "sup",
    "pete": "petai",
    "sambel": "sambal",
    "jojga": "jogja",
    "rica rica": "rica-rica",
    "mie": "mi",
    "satay": "sate",
}
LOWERCASE = {
    "agar", "ala", "antara", "antar", "atas", "atau", "bagai", "bagi",
    "bahwa", "bawah", "dalam", "dan", "dari", "daripada", "dengan", "di",
    "hingga", "karena", "ke", "kecuali", "kepada", "ketika", "luar",
    "melainkan", "oleh", "pada", "per", "sambil", "sampai", "sebagai",
    "sejak", "selama", "serta", "supaya", "tentang", "terhadap", "untuk", "yang",
}
ACRONYMS = {
    "bbq": "BBQ",
    "dki": "DKI",
    "kfc": "KFC",
    "mpasi": "MPASI",
    "uht": "UHT",
}

LEADING_SOURCE_NOISE = re.compile(
    r"^\W*(?:(?:RCP[-_][A-Z0-9]+[-_]\d+)|(?:[A-Z]{1,4}[-_]\d+)|(?:[A-Z]?\d+))"
    r"(?=\s|[.):\]\-])(?:[.)\]]\s*|[-:]\s*|\s+)",
    re.IGNORECASE,
)
PARENTHETICAL_SOURCE_NOISE = re.compile(
    r"\s*\(\s*(?:(?:resep|recipe|no\.?\s*)\s*#?\d+|#?\d+|"
    r"\d+(?:[-\u2013]\d+)?\s*(?:porsi|orang|potong|butir|buah|lembar|bahan|"
    r"gram|gr|kg|ml|liter|menit|jam|servings?|portions?|pieces?))\s*\)",
    re.IGNORECASE,
)


def load_overrides(path: str | Path) -> dict[str, tuple[str, str]]:
    """Load curated names, rejecting malformed or duplicate recipe codes."""
    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"recipe_code", "name", "reason"}
        if not required.issubset(reader.fieldnames or []):
            missing = ", ".join(sorted(required - set(reader.fieldnames or [])))
            raise ValueError(f"Kolom override nama resep tidak lengkap: {missing}")

        overrides = {}
        for line_number, row in enumerate(reader, start=2):
            code = (row.get("recipe_code") or "").strip()
            name = (row.get("name") or "").strip()
            reason = (row.get("reason") or "").strip()
            if not code or not name or not reason:
                raise ValueError(f"Override nama resep tidak lengkap pada baris {line_number}")
            if code in overrides:
                raise ValueError(f"Kode resep duplikat pada override nama: {code}")
            overrides[code] = (name, reason)
        return overrides


def _capitalize(word: str) -> str:
    return "-".join(
        ACRONYMS.get(part.casefold(), part[:1].upper() + part[1:])
        for part in word.split("-")
    )


def standard_name(name: str | None) -> str:
    """Remove leading IDs/count notes and normalize spelling and title case."""
    if name is None:
        return ""
    if not isinstance(name, str):
        raise TypeError("Nama resep harus berupa teks")

    name = unicodedata.normalize("NFC", name)
    name = LEADING_SOURCE_NOISE.sub("", name, count=1)
    name = PARENTHETICAL_SOURCE_NOISE.sub("", name)
    name = re.sub(r"\s+", " ", name).strip(" \t\r\n.,;:-")
    lowered = name.casefold()
    for informal, standard in sorted(SPELLING.items(), key=lambda pair: -len(pair[0])):
        lowered = re.sub(rf"\b{re.escape(informal)}\b", standard, lowered)

    titled = []
    for index, token in enumerate(lowered.split(" ")):
        core = re.sub(r"^\W+|\W+$", "", token)
        if not core:
            titled.append(token)
            continue
        start = token.find(core)
        prefix, suffix = token[:start], token[start + len(core):]
        is_lowercase_task_word = (
            index > 0
            and not prefix.endswith("(")
            and core.casefold() in LOWERCASE
        )
        cased = core if is_lowercase_task_word else _capitalize(core)
        titled.append(prefix + cased + suffix)
    return " ".join(titled)
