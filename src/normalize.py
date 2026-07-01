"""
normalize.py
Pure normalization functions used across the pipeline.
Design doc reference: Section 2 - Canonical Schema & Normalized Formats.
"""
import re
import json
import os

_SKILLS_DICT_PATH = os.path.join(os.path.dirname(__file__), "skills_dictionary.json")
with open(_SKILLS_DICT_PATH, "r", encoding="utf-8") as f:
    SKILLS_DICTIONARY = json.load(f)

# Minimal city -> {region, country} lookup for sample data.
# Kept small and external-style on purpose; extendable without touching logic.
LOCATION_LOOKUP = {
    "bangalore": {"region": "Karnataka", "country": "IN"},
    "bengaluru": {"region": "Karnataka", "country": "IN"},
    "chennai": {"region": "Tamil Nadu", "country": "IN"},
    "mumbai": {"region": "Maharashtra", "country": "IN"},
    "delhi": {"region": "Delhi", "country": "IN"},
    "pune": {"region": "Maharashtra", "country": "IN"},
}

MONTHS = {
    "jan": "01", "january": "01", "feb": "02", "february": "02",
    "mar": "03", "march": "03", "apr": "04", "april": "04",
    "may": "05", "jun": "06", "june": "06", "jul": "07", "july": "07",
    "aug": "08", "august": "08", "sep": "09", "sept": "09", "september": "09",
    "oct": "10", "october": "10", "nov": "11", "november": "11",
    "dec": "12", "december": "12",
}


def normalize_phone(raw, default_country_code="91"):
    """Convert any raw phone string into E.164 format. Returns None if unparseable."""
    if not raw or not str(raw).strip():
        return None
    digits = re.sub(r"[^\d+]", "", str(raw))
    if digits.startswith("+"):
        return digits
    digits = digits.lstrip("0")
    if len(digits) == 10:
        return f"+{default_country_code}{digits}"
    if len(digits) > 10:
        return f"+{digits}"
    return None  # too short to be a valid phone -> honestly null, never guessed


def normalize_date(raw):
    """
    Convert a free-form date string into YYYY-MM (or YYYY if month unknown).
    Returns a tuple (normalized_value, precision) where precision is 'month' or 'year'.
    Returns (None, None) if unparseable.
    """
    if not raw or not str(raw).strip():
        return None, None
    raw = str(raw).strip()

    # ISO-like YYYY-MM or YYYY-MM-DD
    m = re.match(r"^(\d{4})-(\d{2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}", "month"

    # MM/YYYY or MM-YYYY
    m = re.match(r"^(\d{1,2})[/-](\d{4})$", raw)
    if m:
        return f"{m.group(2)}-{m.group(1).zfill(2)}", "month"

    # "March 2021" / "Mar 2021" / "Jun'21"
    m = re.match(r"^([A-Za-z]+)['\s]+(\d{2,4})$", raw)
    if m:
        mon = MONTHS.get(m.group(1).lower())
        year = m.group(2)
        if len(year) == 2:
            year = "20" + year
        if mon:
            return f"{year}-{mon}", "month"

    # Just a year, e.g. "2018"
    m = re.match(r"^(\d{4})$", raw)
    if m:
        return m.group(1), "year"

    # "Present" / "Current" -> treated specially by caller, not a date
    if raw.lower() in ("present", "current", "now"):
        return "present", "present"

    return None, None


def normalize_country(raw):
    """Return ISO-3166 alpha-2 code for a small set of known country names."""
    if not raw:
        return None
    table = {"india": "IN", "in": "IN", "united states": "US", "usa": "US", "us": "US"}
    return table.get(str(raw).strip().lower())


def normalize_location(raw_city):
    """Given a free-text city, return {city, region, country} using LOCATION_LOOKUP."""
    if not raw_city:
        return {"city": None, "region": None, "country": None}
    key = raw_city.strip().lower()
    info = LOCATION_LOOKUP.get(key, {})
    return {
        "city": raw_city.strip().title(),
        "region": info.get("region"),
        "country": info.get("country"),
    }


def normalize_skill(raw_skill):
    """Map a raw skill string to its canonical form via the external dictionary."""
    if not raw_skill:
        return None
    key = raw_skill.strip().lower()
    return SKILLS_DICTIONARY.get(key, raw_skill.strip())


def normalize_name(raw_name):
    if not raw_name:
        return None
    return re.sub(r"\s+", " ", raw_name.strip()).title()


def normalize_email(raw_email):
    if not raw_email:
        return None
    return raw_email.strip().lower()
