"""
extractors/ats_json_extractor.py
Extracts raw candidate records from the ATS JSON blob, whose field names
deliberately do NOT match our canonical names (per problem statement).
"""
import json


def extract(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[WARN] Failed to parse ATS JSON source '{path}': {e}")
        return []

    candidates = data.get("candidates", []) if isinstance(data, dict) else []
    records = []
    for c in candidates:
        records.append({
            "_source_type": "ats_json",
            "_source_file": path,
            "raw_name": c.get("candidate_full_name"),
            "raw_email": c.get("contact_email"),
            "raw_phone": c.get("mobile_no"),
            "raw_company": c.get("employer"),
            "raw_title": c.get("job_title"),
            "raw_applied_date": c.get("applied_date"),
            # ATS blobs sometimes carry a skills list under various field names;
            # try common variants, fall back to empty (never None - absence is explicit).
            "raw_skills": (
                c.get("skills") or
                c.get("skill_set") or
                c.get("technologies") or
                []
            ),
        })
    return records
