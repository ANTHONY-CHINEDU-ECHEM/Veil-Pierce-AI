"""Text normalisation for names, companies, jurisdictions and addresses.

Registry data is typed by hand by millions of filers, so the same person,
company or address appears under many spellings. Everything that compares
strings in Veil Pierce AI goes through the functions in this module first.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

_NON_WORD = re.compile(r"[^\w\s]|_")
_SPACES = re.compile(r"\s+")
_DIGITS = re.compile(r"\d+")

TITLES = {"MR", "MRS", "MS", "MISS", "DR", "SIR", "DAME", "LORD", "LADY", "PROF", "PROFESSOR", "REV", "HON", "MX"}
SURNAME_PARTICLES = {"DE", "DA", "DI", "DU", "VAN", "VON", "DER", "DEN", "LA", "LE", "EL", "AL", "BIN", "BINTI", "IBN", "ST", "MAC", "DOS", "DEL"}

LEGAL_FORM_MAP = {
    "LIMITED": "LTD",
    "LTD": "LTD",
    "LLP": "LLP",
    "LP": "LP",
    "PLC": "PLC",
    "INCORPORATED": "INC",
    "INC": "INC",
    "CORPORATION": "CORP",
    "CORP": "CORP",
    "COMPANY": "CO",
    "CO": "CO",
    "GMBH": "GMBH",
    "AG": "AG",
    "SA": "SA",
    "SARL": "SARL",
    "BV": "BV",
    "NV": "NV",
    "KK": "KK",
    "AB": "AB",
    "LLC": "LLC",
    "PTE": "PTE",
    "PTY": "PTY",
}
LEGAL_FORM_TOKENS = set(LEGAL_FORM_MAP.values())
NAME_NOISE_TOKENS = {"THE", "AND", "UK"}

ADDRESS_ABBREVIATIONS = {
    "ST": "STREET",
    "RD": "ROAD",
    "AVE": "AVENUE",
    "AV": "AVENUE",
    "LN": "LANE",
    "CL": "CLOSE",
    "CT": "COURT",
    "DR": "DRIVE",
    "SQ": "SQUARE",
    "PL": "PLACE",
    "STE": "SUITE",
    "FLR": "FLOOR",
    "FL": "FLOOR",
    "BLDG": "BUILDING",
    "HSE": "HOUSE",
}
UNIT_WORDS = {"SUITE", "OFFICE", "UNIT", "FLOOR", "FLAT", "ROOM", "APARTMENT", "BOX", "DEPT", "DEPARTMENT"}
ORDINAL_SUFFIXES = ("ST", "ND", "RD", "TH")


def strip_accents(text: str) -> str:
    """Remove diacritics so that Jose and its accented spelling compare equal."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def norm_text(text: object) -> str:
    """Upper case, strip accents and punctuation, collapse whitespace."""
    if text is None:
        return ""
    value = str(text)
    if not value or value == "nan":
        return ""
    value = strip_accents(value).upper().replace("&", " AND ")
    value = _NON_WORD.sub(" ", value)
    return _SPACES.sub(" ", value).strip()


@lru_cache(maxsize=500_000)
def norm_company_name(name: str) -> str:
    """Canonical company name used for exact comparison across datasets.

    Legal form words are mapped to one spelling, single letters that came from
    dotted abbreviations are joined (L P becomes LP), and filler words such as
    THE and AND are removed.
    """
    tokens = norm_text(name).split()
    joined: list[str] = []
    buffer = ""
    for token in tokens:
        if len(token) == 1 and token.isalpha():
            buffer += token
            continue
        if buffer:
            joined.append(buffer)
            buffer = ""
        joined.append(token)
    if buffer:
        joined.append(buffer)
    out = [LEGAL_FORM_MAP.get(tok, tok) for tok in joined if tok not in NAME_NOISE_TOKENS]
    return " ".join(out)


@lru_cache(maxsize=500_000)
def company_core(name: str) -> str:
    """Company name with every legal form token removed.

    Two filings that differ only in LTD against LIMITED, or that omit the
    legal form completely, share the same core.
    """
    tokens = [tok for tok in norm_company_name(name).split() if tok not in LEGAL_FORM_TOKENS]
    return " ".join(tokens)


def parse_person_name(raw: object) -> tuple[str, str, str]:
    """Split a raw person name into surname, first forename and other forenames.

    Handles the officer register layout (SURNAME, Forename Middle) and the
    natural order layout used in the control register (Mr Forename Middle
    Surname). Returned parts are normalised upper case tokens.
    """
    text = "" if raw is None else str(raw)
    if "," in text:
        left, right = text.split(",", 1)
        surname = norm_text(left)
        given = [tok for tok in norm_text(right).split() if tok not in TITLES]
    else:
        tokens = [tok for tok in norm_text(text).split() if tok not in TITLES]
        if not tokens:
            return "", "", ""
        cut = len(tokens) - 1
        while cut > 1 and tokens[cut - 1] in SURNAME_PARTICLES:
            cut -= 1
        surname = " ".join(tokens[cut:])
        given = tokens[:cut]
    first = given[0] if given else ""
    rest = " ".join(given[1:]) if len(given) > 1 else ""
    return surname, first, rest


_TRANSLIT_PAIRS = (
    ("SCH", "S"),
    ("TCH", "C"),
    ("DZH", "J"),
    ("ZH", "J"),
    ("KH", "K"),
    ("GH", "G"),
    ("PH", "F"),
    ("CK", "K"),
    ("SH", "S"),
    ("CH", "C"),
    ("TS", "S"),
    ("TZ", "S"),
    ("X", "KS"),
    ("OU", "U"),
    ("EE", "I"),
    ("OO", "U"),
)
_TRANSLIT_SINGLE = str.maketrans({"Q": "K", "Z": "S", "W": "V", "Y": "I", "C": "K"})
_VOWELS = set("AEIOU")


@lru_cache(maxsize=500_000)
def translit_key(token: str) -> str:
    """Consonant skeleton that is stable across common transliterations.

    MOHAMMED, MUHAMMAD and MOHAMED all map to MHMD. ALEXEI and ALEKSEY both
    map to ALKS. The key is used for blocking only, never as proof of a match.
    """
    value = norm_text(token).replace(" ", "")
    if not value:
        return ""
    for src, dst in _TRANSLIT_PAIRS:
        value = value.replace(src, dst)
    value = value.translate(_TRANSLIT_SINGLE)
    out = []
    previous = ""
    for index, ch in enumerate(value):
        if ch in _VOWELS:
            if index == 0:
                out.append("A")
        elif ch == "H" and index > 0:
            pass
        elif ch != previous:
            out.append(ch)
        previous = ch
    return "".join(out)


def norm_postcode(postcode: object) -> str:
    """Upper case postcode with all spacing removed."""
    return norm_text(postcode).replace(" ", "")


def _is_ordinal(token: str) -> bool:
    return len(token) > 2 and token[:-2].isdigit() and token.endswith(ORDINAL_SUFFIXES)


@lru_cache(maxsize=500_000)
def address_key(line1: str, postcode: str) -> str:
    """Key that identifies a building regardless of suite, floor or formatting.

    Unit phrases such as SUITE 12 or 2ND FLOOR are dropped, abbreviations are
    expanded, and the key is built from the postcode, the building number and
    the first word of the street name.
    """
    tokens = [ADDRESS_ABBREVIATIONS.get(tok, tok) for tok in norm_text(line1).split()]
    kept: list[str] = []
    skip_next_number = False
    ordinal_before = False
    for position, token in enumerate(tokens):
        nxt = tokens[position + 1] if position + 1 < len(tokens) else ""
        if _is_ordinal(token) and nxt in UNIT_WORDS:
            ordinal_before = True
            continue
        if token in UNIT_WORDS:
            skip_next_number = not ordinal_before
            ordinal_before = False
            continue
        if skip_next_number and (token.isdigit() or (len(token) <= 3 and any(c.isdigit() for c in token))):
            skip_next_number = False
            continue
        skip_next_number = False
        kept.append(token)
    number = ""
    street = ""
    for position, token in enumerate(kept):
        if token[0].isdigit():
            number = token
            street = kept[position + 1] if position + 1 < len(kept) else ""
            break
    if not number and kept:
        street = kept[0]
    return f"{norm_postcode(postcode)}|{number}|{street}"


def canonical_jurisdiction(raw: object, aliases: dict[str, str]) -> str:
    """Map a free text country or place of registration to a canonical name."""
    value = norm_text(raw)
    if not value:
        return ""
    return aliases.get(value, value)


def name_tokens(name: object) -> list[str]:
    """Normalised tokens of a name with titles removed."""
    return [tok for tok in norm_text(name).split() if tok not in TITLES]


def extract_numbers(text: str) -> list[str]:
    """All integer strings that appear in a piece of text."""
    return _DIGITS.findall(text or "")
