"""Clear, standard recipe names shown to users.

Curated renames and exclusions live in mapping/recipe_name_overrides.csv; the
rules below only normalize spelling, casing and source noise such as numbering.
"""

import csv
import re

EXCLUDE = "exclude"
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
}
LOWERCASE = {"dan", "dengan", "ala", "di", "ke", "untuk", "atau"}


def load_overrides(path):
    with open(path, encoding="utf-8") as handle:
        return {row["recipe_code"]: (row["name"], row["reason"]) for row in csv.DictReader(handle)}


def _capitalize(word):
    return "-".join(part[:1].upper() + part[1:] for part in word.split("-"))


def standard_name(name):
    """Drop numbering/codes, standardize spelling and use consistent title case."""
    name = re.sub(r"^\W*[A-Za-z]?\d+[.)]?\s+", "", name)
    name = re.sub(r"\s*\([^)]*\d[^)]*\)", "", name)
    name = re.sub(r"\s+", " ", name).strip(" .,-")
    lowered = name.casefold()
    for informal, standard in SPELLING.items():
        lowered = re.sub(rf"\b{informal}\b", standard, lowered)
    words = lowered.split(" ")
    titled = [
        word if index and word in LOWERCASE else _capitalize(word)
        for index, word in enumerate(words)
    ]
    # Words opening a parenthesis are capitalized too: "(pempek ..." -> "(Pempek ...".
    return re.sub(r"\((\w)", lambda m: "(" + m[1].upper(), " ".join(titled))
