"""Shared deterministic normalisation helpers for vendor checks."""

import re

LEGAL_SUFFIXES = {
    "pte",
    "ltd",
    "limited",
    "llc",
    "inc",
    "pty",
    "gmbh",
    "fze",
    "llp",
    "co",
    "corp",
    "corporation",
    "plc",
}
COUNTRY_ALIASES = {
    "sg": "singapore",
    "sgp": "singapore",
    "republic of singapore": "singapore",
}


def normalise_country(country: str | None) -> str:
    """Normalise known country aliases without guessing an unknown country."""

    value = re.sub(r"\s+", " ", (country or "").strip().lower())
    return COUNTRY_ALIASES.get(value, value)


def normalise_name(name: str | None, *, drop_legal_suffixes: bool = True) -> str:
    """Canonicalise names for deterministic matching; optionally retain legal suffixes."""

    value = (name or "").lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    parts = value.split()
    if drop_legal_suffixes:
        while parts and parts[-1] in LEGAL_SUFFIXES:
            parts.pop()
    return " ".join(parts)
