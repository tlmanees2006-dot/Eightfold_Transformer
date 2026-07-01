"""
merge.py
Design doc Section 3 - 'Winner selection (per field type)' + Section 2 schema.

Takes a cluster of normalized records (all believed to be the same person)
and produces ONE canonical profile dict matching the default output schema,
with provenance[] and per-field confidence populated.

Source priority hierarchy (highest trust first), per field type:
  identity fields (name/email/phone): csv/ats_json > resume > notes
  current role/title:                 most-recent source > resume > csv
  experience/education history:       resume > notes > csv/ats_json
  skills:                             UNION across all sources, not override
"""
import hashlib
import difflib
from src import confidence as conf_mod

IDENTITY_PRIORITY = {"csv": 3, "ats_json": 3, "resume": 2, "notes": 1}
HISTORY_PRIORITY = {"resume": 3, "notes": 2, "csv": 1, "ats_json": 1}


def _candidate_id(records):
    for r in records:
        if r.get("norm_email"):
            return "cand_" + hashlib.sha1(r["norm_email"].encode()).hexdigest()[:10]
    for r in records:
        if r.get("norm_phone"):
            return "cand_" + hashlib.sha1(r["norm_phone"].encode()).hexdigest()[:10]
    for r in records:
        if r.get("norm_name"):
            h = hashlib.sha1(r["norm_name"].encode()).hexdigest()[:10]
            return f"cand_{h}_lowconf"
    return "cand_unknown_" + hashlib.sha1(str(records).encode()).hexdigest()[:6]


def _similar(a, b, threshold=0.8):
    if not a or not b:
        return False
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


def _pick_winner(records, field_key, priority_table, most_recent_source_type=None):
    """
    Generic winner-picker: among records that have a non-null value for
    field_key, choose the one from the highest-priority source. On a tie,
    prefer the most recent source. Returns (winning_value, winning_source_type,
    list_of_contributing_source_types, near_duplicate_collapsed: bool).
    """
    candidates = [(r.get(field_key), r["_source_type"]) for r in records if r.get(field_key)]
    if not candidates:
        return None, None, [], False

    contributing_sources = [s for _, s in candidates]

    # collapse near-identical string values (avoid false conflicts)
    collapsed = []
    for val, src in candidates:
        merged_into_existing = False
        if isinstance(val, str):
            for i, (existing_val, existing_src, existing_count) in enumerate(collapsed):
                if isinstance(existing_val, str) and _similar(val, existing_val):
                    # keep the longer/more detailed phrasing
                    better = val if len(val) > len(existing_val) else existing_val
                    collapsed[i] = (better, existing_src, existing_count + 1)
                    merged_into_existing = True
                    break
        if not merged_into_existing:
            collapsed.append((val, src, 1))

    near_dup_collapsed = len(collapsed) < len(candidates)

    def sort_key(item):
        val, src, count = item
        prio = priority_table.get(src, 0)
        recency_bonus = 1 if src == most_recent_source_type else 0
        return (prio, recency_bonus, count)

    collapsed.sort(key=sort_key, reverse=True)
    winning_value, winning_source, _ = collapsed[0]
    return winning_value, winning_source, contributing_sources, near_dup_collapsed


def _merge_skills(records):
    """Union of skills across all sources - agreement raises confidence, never overrides."""
    skill_sources = {}
    for r in records:
        for s in r.get("norm_skills", []) or []:
            skill_sources.setdefault(s, set()).add(r["_source_type"])
    result = []
    for skill, sources in skill_sources.items():
        result.append({
            "name": skill,
            "confidence": round(min(0.5 + 0.2 * len(sources), 1.0), 2),
            "sources": sorted(sources),
        })
    return sorted(result, key=lambda x: -x["confidence"])


def _merge_experience(records):
    seen = []
    for r in records:
        for exp in r.get("norm_experience", []) or []:
            if not any(_similar(exp.get("company", ""), s.get("company", "")) for s in seen):
                seen.append(exp)
    return seen


def _derive_years_experience(experience_list):
    """Sum up date ranges from experience entries; returns (years, method)."""
    total_months = 0
    found_any = False
    for exp in experience_list:
        start = exp.get("start_normalized")
        end = exp.get("end_normalized")
        if not start:
            continue
        try:
            sy, sm = int(start[:4]), int(start[5:7]) if len(start) > 4 else 1
        except Exception:
            continue
        if end == "present" or end is None:
            import datetime
            ey, em = datetime.date.today().year, datetime.date.today().month
        else:
            try:
                ey, em = int(end[:4]), int(end[5:7]) if len(end) > 4 else 12
            except Exception:
                continue
        months = (ey - sy) * 12 + (em - sm)
        if months > 0:
            total_months += months
            found_any = True
    if not found_any:
        return None, None
    return round(total_months / 12, 1), "derived"


def merge_cluster(records):
    """
    records: list of normalized records (all in one matched cluster).
    Returns a canonical profile dict matching the default schema, plus
    internal '_field_confidence' map used by confidence.overall_confidence().
    """
    provenance = []
    field_confidences = {}
    data_quality_flags = []

    source_types_present = [r["_source_type"] for r in records]
    most_recent = None
    dated = [(r.get("raw_applied_date"), r["_source_type"]) for r in records if r.get("raw_applied_date")]
    if dated:
        dated.sort(reverse=True)
        most_recent = dated[0][1]

    # --- Identity fields ---
    name_val, name_src, name_contrib, _ = _pick_winner(records, "norm_name", IDENTITY_PRIORITY)
    email_val, email_src, email_contrib, _ = _pick_winner(records, "norm_email", IDENTITY_PRIORITY)
    phone_val, phone_src, phone_contrib, _ = _pick_winner(records, "norm_phone", IDENTITY_PRIORITY)

    if not email_val:
        data_quality_flags.append("no_email_present")
    if not phone_val:
        data_quality_flags.append("no_phone_present")
    if not email_val and not phone_val:
        data_quality_flags.append("no_stable_identifier")
    if len(records) == 1:
        data_quality_flags.append("single_source")

    field_confidences["full_name"] = conf_mod.field_confidence(name_contrib, name_src)
    field_confidences["emails"] = conf_mod.field_confidence(email_contrib, email_src)
    field_confidences["phones"] = conf_mod.field_confidence(phone_contrib, phone_src)

    for field, src, val, prov_method in [
        ("full_name", name_src, name_val, "extracted"),
        ("emails", email_src, email_val, "extracted"),
        ("phones", phone_src, phone_val, "extracted"),
    ]:
        if val:
            provenance.append({
                "field": field, "source": src, "method": prov_method,
                "confidence": field_confidences.get(field, 0.0),
            })

    # --- Current role/title (most-recent source > resume > csv) ---
    title_priority = {"ats_json": 3 if most_recent == "ats_json" else 1,
                       "csv": 3 if most_recent == "csv" else 1,
                       "resume": 2, "notes": 1}
    title_val, title_src, title_contrib, title_collapsed = _pick_winner(
        records, "raw_title", title_priority, most_recent_source_type=most_recent)
    company_val, company_src, company_contrib, _ = _pick_winner(
        records, "raw_company", title_priority, most_recent_source_type=most_recent)

    headline_val, headline_src, headline_contrib, _ = _pick_winner(records, "norm_headline", HISTORY_PRIORITY)
    field_confidences["headline"] = conf_mod.field_confidence(headline_contrib, headline_src) if headline_val else None
    if headline_val:
        provenance.append({"field": "headline", "source": headline_src, "method": "extracted",
                            "confidence": field_confidences["headline"]})

    # --- Experience / Education (resume > notes > csv/ats) ---
    experience = _merge_experience(records)
    for exp in experience:
        provenance.append({"field": "experience", "source": exp.get("_source_type", "resume"),
                            "method": "extracted", "confidence": 0.8})

    education_val, education_src, education_contrib, _ = _pick_winner(records, "norm_education", HISTORY_PRIORITY)
    education_entry = next(
        (r.get("norm_education_entry") for r in records
         if r["_source_type"] == education_src and r.get("norm_education_entry")),
        None,
    )

    # --- Skills: union, not override ---
    skills = _merge_skills(records)
    field_confidences["skills"] = round(sum(s["confidence"] for s in skills) / len(skills), 3) if skills else None
    for s in skills:
        provenance.append({"field": "skills", "source": "+".join(s["sources"]), "method": "merged_union",
                            "confidence": s["confidence"]})

    # --- years_experience: stated takes priority over derived ---
    stated_years = next((r.get("raw_years_experience") for r in records if r.get("raw_years_experience")), None)
    if stated_years:
        years_experience, years_method = stated_years, "stated"
    else:
        years_experience, years_method = _derive_years_experience(experience)
    field_confidences["years_experience"] = 0.85 if years_method == "stated" else (0.6 if years_method == "derived" else None)
    if years_experience is not None:
        provenance.append({"field": "years_experience", "source": "computed", "method": years_method,
                            "confidence": field_confidences["years_experience"]})

    # --- location ---
    location = next((r.get("norm_location") for r in records if r.get("norm_location") and r["norm_location"].get("city")), None)
    if not location:
        location = {"city": None, "region": None, "country": None}

    # --- links ---
    links = {"linkedin": None, "github": None, "portfolio": None, "other": []}
    for r in records:
        if r.get("raw_portfolio"):
            links["portfolio"] = r["raw_portfolio"]
        if r.get("raw_linkedin"):
            links["linkedin"] = r["raw_linkedin"]

    candidate_id = _candidate_id(records)

    profile = {
        "candidate_id": candidate_id,
        "full_name": name_val,
        "emails": [email_val] if email_val else [],
        "phones": [phone_val] if phone_val else [],
        "location": location,
        "links": links,
        "headline": headline_val,
        "years_experience": years_experience,
        "skills": skills,
        "experience": [
            {
                "company": e.get("company"),
                "title": e.get("title"),
                "start": e.get("start_normalized"),
                "end": e.get("end_normalized"),
                "summary": e.get("summary"),
            } for e in experience
        ],
        "education": [{
            "institution": education_entry.get("raw_institution") if education_entry else None,
            "degree": education_entry.get("raw_degree") if education_entry else None,
            "field": education_entry.get("raw_field") if education_entry else None,
            "end_year": education_entry.get("raw_end_year") if education_entry else None,
            "raw_text": education_val,
        }] if education_val else [],
        "provenance": provenance,
        "data_quality_flags": data_quality_flags,
    }

    # title/company are not in the default schema directly but are folded into
    # the most recent experience entry's title/company if no experience exists.
    if title_val and not profile["experience"]:
        profile["experience"] = [{
            "company": company_val, "title": title_val, "start": None, "end": "present", "summary": None,
        }]

    profile["_field_confidence_map"] = field_confidences
    return profile
