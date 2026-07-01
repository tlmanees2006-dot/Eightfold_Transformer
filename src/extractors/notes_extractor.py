"""
extractors/notes_extractor.py
Extracts candidate mentions from free-text recruiter notes. Each entry is
separated by '---'. Uses lightweight regex/pattern extraction, deliberately
not a trained NLP/NER model (explainability over marginal accuracy - see
design doc scope decisions).
"""
import re
import json
import os

EMAIL_RE = re.compile(r"[\w.\-+]+@[\w\-]+\.[\w.\-]+")
PHONE_RE = re.compile(r"\b\d{10}\b")
YEARS_EXP_RE = re.compile(r"~?(\d+)\s*(?:\+)?\s*(?:yrs|years)", re.IGNORECASE)
PORTFOLIO_RE = re.compile(r"Portfolio:\s*([\w\-]+\.(?:design|com|dev|io|me))", re.IGNORECASE)
LINKEDIN_RE = re.compile(r"(linkedin\.com/in/[\w\-]+)", re.IGNORECASE)

NAME_PATTERNS = [
    re.compile(r"(?:Call with|Spoke (?:to|with)|Quick chat with)\s+([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)+)"),
]

# Load the same skills dictionary the normalizer uses so keyword detection
# is consistent with canonicalization (config-driven, not a separate hardcoded list).
_SKILLS_DICT_PATH = os.path.join(os.path.dirname(__file__), "..", "skills_dictionary.json")
with open(_SKILLS_DICT_PATH, "r", encoding="utf-8") as _f:
    _SKILLS_DICT = json.load(_f)

# Build a set of all known skill aliases for fast text scanning.
# We match the longest variants first to avoid "JS" matching inside "Node.js".
_SKILL_VARIANTS = sorted(_SKILLS_DICT.keys(), key=len, reverse=True)


def _extract_skills_from_text(text):
    """
    Scans free text for any known skill keyword from the skills dictionary.
    Returns a list of raw (pre-canonicalization) skill strings found.
    Canonicalization happens later in normalize.py, same as every other source.
    """
    found = []
    lowered = text.lower()
    for variant in _SKILL_VARIANTS:
        # Use word-boundary-aware search to avoid partial matches
        pattern = r"(?<![a-z0-9])" + re.escape(variant) + r"(?![a-z0-9])"
        if re.search(pattern, lowered):
            found.append(variant)
    return found


def _extract_name(entry_text):
    for pattern in NAME_PATTERNS:
        m = pattern.search(entry_text)
        if m:
            return m.group(1).strip()
    return None


def _extract_company(entry_text):
    m = re.search(r"(?:at|with)\s+([A-Z][a-zA-Z]+)\b(?!\.com)", entry_text)
    return m.group(1) if m else None


def _extract_title(entry_text):
    m = re.search(r"(?:is a|she's a|he's a)\s+([A-Za-z ]+?)(?:\swith|\.|,)", entry_text)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"\b(Backend dev(?:eloper)?|Product Designer|QA Engineer)\b", entry_text, re.IGNORECASE)
    return m2.group(1) if m2 else None


def extract(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        print(f"[WARN] Failed to read notes file '{path}': {e}")
        return []

    entries = [e.strip() for e in text.split("---") if e.strip()]
    records = []
    for entry in entries:
        email_match = EMAIL_RE.search(entry)
        phone_match = PHONE_RE.search(entry)
        years_match = YEARS_EXP_RE.search(entry)
        portfolio_match = PORTFOLIO_RE.search(entry)
        linkedin_match = LINKEDIN_RE.search(entry)

        records.append({
            "_source_type": "notes",
            "_source_file": path,
            "raw_name": _extract_name(entry),
            "raw_email": email_match.group(0) if email_match else None,
            "raw_phone": phone_match.group(0) if phone_match else None,
            "raw_company": _extract_company(entry),
            "raw_title": _extract_title(entry),
            "raw_years_experience": int(years_match.group(1)) if years_match else None,
            "raw_portfolio": portfolio_match.group(1) if portfolio_match else None,
            "raw_linkedin": linkedin_match.group(1) if linkedin_match else None,
            "raw_skills": _extract_skills_from_text(entry),  # keyword scan against skills_dictionary
            "raw_free_text": entry,
        })
    return records
