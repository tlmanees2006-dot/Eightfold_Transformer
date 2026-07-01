"""
extractors/resume_extractor.py
Extracts a candidate profile from a resume PDF/DOCX using text extraction +
section-header heuristics (no ML/NLP model - kept explainable, per design doc
scope decision).
"""
import re
import os


def _read_pdf_text(path):
    import pdfplumber
    text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            # x_tolerance lowered from pdfplumber's default (3) to 2: some resume
            # PDFs have tight inter-word kerning that the default tolerance reads
            # as a single run-together word (e.g. "October2023"). 2 is verified to
            # restore normal word spacing without over-splitting real single words.
            page_text = page.extract_text(x_tolerance=2) or ""
            text += page_text + "\n"
    return text


def _read_docx_text(path):
    import docx
    doc = docx.Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


# Maps recognized header spellings to a canonical section bucket. "TECHNICAL
# SKILLS" is an alias for "SKILLS" so both spellings land in the same bucket.
# "PROJECTS" is recognized (but otherwise unused) purely so its content stops
# bleeding into EXPERIENCE when no header for it existed before.
SECTION_HEADER_ALIASES = {
    "SUMMARY": "SUMMARY",
    "EXPERIENCE": "EXPERIENCE",
    "EDUCATION": "EDUCATION",
    "SKILLS": "SKILLS",
    "TECHNICAL SKILLS": "SKILLS",
    "PROJECTS": "PROJECTS",
}
SECTION_HEADERS = list(SECTION_HEADER_ALIASES.keys())


def _split_sections(text):
    sections = {}
    current = "HEADER"
    sections[current] = []
    for line in text.split("\n"):
        stripped = line.strip()
        upper = stripped.upper()
        # startswith (not exact ==) because some PDFs render two side-by-side
        # resume columns as one merged line (e.g. "TECHNICAL SKILLS CERTIFICATIONS").
        matched_alias = next((h for h in SECTION_HEADER_ALIASES if upper.startswith(h)), None)
        if matched_alias:
            current = SECTION_HEADER_ALIASES[matched_alias]
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


CONTACT_LINE_RE = re.compile(
    r"@|\(cid:\d+\)|linkedin\.com|github\.com|(\+?\d[\d\s\-]{7,}\d)"
)


def _looks_like_contact_line(line):
    """
    True if a line is a contact/icon row (email, phone, broken glyph codes from
    icon fonts used for LinkedIn/GitHub/phone symbols) rather than resume prose.
    """
    if CONTACT_LINE_RE.search(line):
        return True
    alnum_or_space = sum(1 for c in line if c.isalnum() or c.isspace())
    if line and (alnum_or_space / len(line)) < 0.6:
        return True
    return False


EMAIL_RE = re.compile(r"[\w.\-+]+@[\w\-]+\.[\w.\-]+")
PHONE_RE = re.compile(r"(\+?\d[\d\s\-]{8,}\d)")
DATE_RANGE_RE = re.compile(
    r"([A-Za-z]+\s+\d{4}|\d{1,2}/\d{4})\s*[-–—]\s*(Present|Current|[A-Za-z]+\s+\d{4}|\d{1,2}/\d{4})",
    re.IGNORECASE,
)

# Same dictionary/technique as extractors/notes_extractor.py, so skill
# detection is consistent across source types instead of relying on the
# resume's own (inconsistent) bullet/comma separators.
import json as _json
_SKILLS_DICT_PATH = os.path.join(os.path.dirname(__file__), "..", "skills_dictionary.json")
with open(_SKILLS_DICT_PATH, "r", encoding="utf-8") as _f:
    _SKILLS_DICT = _json.load(_f)
_SKILL_VARIANTS = sorted(_SKILLS_DICT.keys(), key=len, reverse=True)


def _extract_skills_from_text(text):
    found = []
    lowered = text.lower()
    for variant in _SKILL_VARIANTS:
        pattern = r"(?<![a-z0-9])" + re.escape(variant) + r"(?![a-z0-9])"
        if re.search(pattern, lowered):
            found.append(variant)
    return found


DEGREE_RE = re.compile(
    r"(B\.?E\.?|B\.?Tech\.?|M\.?Tech\.?|B\.?Sc\.?|M\.?Sc\.?|MBA|MCA|BCA|Ph\.?D\.?|Bachelor's|Master's|Diploma)",
    re.IGNORECASE,
)
EDU_YEAR_RE = re.compile(r"(?:19|20)\d{2}")


def _parse_education_entry(education_text):
    """
    Best-effort structured parse of the EDUCATION section into one entry
    (institution, degree, field, end_year). Regex/heuristic based, same
    explainability scope as the rest of this extractor - unrecognized
    formats degrade to raw_text only, never an invented value.
    """
    if not education_text or not education_text.strip():
        return None

    lines = [l.strip() for l in education_text.split("\n") if l.strip()]
    if not lines:
        return None

    institution_line = lines[0]
    institution = re.split(r"\s[-–—]\s", institution_line)[0].strip() or None

    rest_text = "\n".join(lines[1:]) if len(lines) > 1 else institution_line
    degree, field = None, None
    degree_match = DEGREE_RE.search(rest_text)
    if degree_match:
        degree = degree_match.group(1)
        after_degree = rest_text[degree_match.end():]
        field_match = re.match(r"\s*\.?\s*([A-Za-z &]+)", after_degree)
        if field_match:
            field = field_match.group(1).strip(" ,.")
            field = re.split(r"Pre-?Final|Final Year|Current|CGPA", field, flags=re.IGNORECASE)[0].strip()
            # Some PDFs drop spaces between words (e.g. "ComputerScience");
            # insert a space at lower->UPPER letter boundaries as a display fix.
            field = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", field) or None

    years = EDU_YEAR_RE.findall(education_text)
    end_year = int(years[-1]) if years else None

    return {
        "raw_institution": institution,
        "raw_degree": degree,
        "raw_field": field,
        "raw_end_year": end_year,
        "raw_text": education_text,
    }


def extract(path):
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".pdf":
            text = _read_pdf_text(path)
        elif ext == ".docx":
            text = _read_docx_text(path)
        else:
            print(f"[WARN] Unsupported resume format for '{path}'")
            return []
    except Exception as e:
        print(f"[WARN] Failed to read resume '{path}': {e}")
        return []

    if not text.strip():
        print(f"[WARN] Resume '{path}' produced no extractable text (possibly scanned/garbled).")
        return []

    lines = [l for l in text.split("\n") if l.strip()]
    name = lines[0].strip() if lines else None

    headline = None
    for candidate in lines[1:5]:
        candidate = candidate.strip()
        if candidate.upper() in [h for h in SECTION_HEADERS]:
            break  # hit a section header before finding a real headline line
        if _looks_like_contact_line(candidate):
            continue
        headline = candidate
        break

    email_match = EMAIL_RE.search(text)
    raw_email = email_match.group(0) if email_match else None

    phone_match = PHONE_RE.search(text)
    raw_phone = phone_match.group(0) if phone_match else None

    sections = _split_sections(text)

    # Experience entries: lines containing a date range are treated as job headers
    experience_entries = []
    exp_text = sections.get("EXPERIENCE", "")
    for line in exp_text.split("\n"):
        dr = DATE_RANGE_RE.search(line)
        if dr:
            before_dates = line[:dr.start()].strip(" -—–\u2014")
            if "|" in before_dates:
                company_title = before_dates.split("|")
            elif "—" in before_dates:
                company_title = before_dates.split("—")
            else:
                company_title = before_dates.split("-")
            company = company_title[0].strip() if company_title else before_dates
            title = company_title[1].strip() if len(company_title) > 1 else None
            experience_entries.append({
                "raw_company": company,
                "raw_title": title,
                "raw_start": dr.group(1),
                "raw_end": dr.group(2),
            })

    skills_text = sections.get("SKILLS", "")
    raw_skills = _extract_skills_from_text(skills_text)

    education_text = sections.get("EDUCATION", "")
    education_entry = _parse_education_entry(education_text)

    record = {
        "_source_type": "resume",
        "_source_file": path,
        "raw_name": name,
        "raw_headline": headline,
        "raw_email": raw_email,
        "raw_phone": raw_phone,
        "raw_experience": experience_entries,
        "raw_education_text": education_text,
        "raw_education_entry": education_entry,
        "raw_skills": raw_skills,
        "raw_summary": sections.get("SUMMARY", ""),
        "raw_full_text": text,
    }
    return [record]
