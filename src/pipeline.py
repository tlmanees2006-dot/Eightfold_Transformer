"""
pipeline.py
Orchestrates the full pipeline exactly as described in the Stage 1 design doc:
  Detect -> Extract -> Normalize -> Block -> Match -> Merge+Confidence -> Project -> Validate

Public entry point: run_pipeline(sources_dir, configs) -> dict of {config_name: output_list}
Also exposes run_canonical(sources_dir) for the --explain CLI feature.
"""
import os
import glob

from src import detect
from src.extractors import csv_extractor, ats_json_extractor, resume_extractor, notes_extractor
from src import normalize as norm
from src import blocking, match, merge, project as project_mod, validate, confidence as conf_mod

EXTRACTOR_MAP = {
    detect.SOURCE_CSV: csv_extractor.extract,
    detect.SOURCE_ATS_JSON: ats_json_extractor.extract,
    detect.SOURCE_RESUME: resume_extractor.extract,
    detect.SOURCE_NOTES: notes_extractor.extract,
}

# Known city tokens for crude location extraction from free text (kept small,
# extendable - mirrors normalize.LOCATION_LOOKUP).
KNOWN_CITIES = list(norm.LOCATION_LOOKUP.keys())


def _find_city_in_text(text):
    if not text:
        return None
    lowered = text.lower()
    for city in KNOWN_CITIES:
        if city in lowered:
            return city
    return None


def normalize_record(raw):
    """Adapter: raw extractor output -> normalized record used by blocking/match/merge."""
    rec = dict(raw)  # shallow copy, keep raw_* fields for provenance/debugging
    rec["norm_name"] = norm.normalize_name(raw.get("raw_name"))
    rec["norm_email"] = norm.normalize_email(raw.get("raw_email"))
    rec["norm_phone"] = norm.normalize_phone(raw.get("raw_phone"))
    rec["norm_headline"] = raw.get("raw_headline")
    rec["norm_education"] = raw.get("raw_education_text")
    rec["norm_education_entry"] = raw.get("raw_education_entry")

    raw_skills = raw.get("raw_skills") or []
    rec["norm_skills"] = [norm.normalize_skill(s) for s in raw_skills if s]

    raw_experience = raw.get("raw_experience") or []
    normalized_experience = []
    for exp in raw_experience:
        start_norm, _ = norm.normalize_date(exp.get("raw_start"))
        end_raw = exp.get("raw_end")
        if end_raw and end_raw.strip().lower() in ("present", "current"):
            end_norm = "present"
        else:
            end_norm, _ = norm.normalize_date(end_raw)
        normalized_experience.append({
            "company": exp.get("raw_company"),
            "title": exp.get("raw_title"),
            "start_normalized": start_norm,
            "end_normalized": end_norm,
            "summary": None,
            "_source_type": raw["_source_type"],
        })
    rec["norm_experience"] = normalized_experience

    location_text = raw.get("raw_full_text") or raw.get("raw_free_text") or ""
    city = _find_city_in_text(location_text)
    rec["norm_location"] = norm.normalize_location(city) if city else None

    return rec


def run_detect_and_extract(sources_dir):
    """
    Returns (raw_records, source_log) where source_log records what happened
    to each discovered file (parsed / skipped / failed) for transparency
    and the robustness requirement (garbage source must not crash the run).
    """
    raw_records = []
    source_log = []

    all_files = sorted(glob.glob(os.path.join(sources_dir, "**", "*"), recursive=True))
    all_files = [f for f in all_files if os.path.isfile(f)]

    for path in all_files:
        source_type = detect.detect_source_type(path)
        if source_type == detect.SOURCE_UNKNOWN:
            source_log.append({"file": path, "status": "skipped", "reason": "unrecognized or unreadable"})
            continue
        extractor = EXTRACTOR_MAP.get(source_type)
        try:
            records = extractor(path)
            raw_records.extend(records)
            source_log.append({"file": path, "status": "parsed", "type": source_type,
                                "records_found": len(records)})
        except Exception as e:
            source_log.append({"file": path, "status": "failed", "reason": str(e)})
            continue  # never crash the whole run on one bad source

    return raw_records, source_log


def run_canonical(sources_dir):
    """Runs Detect->Extract->Normalize->Block->Match->Merge and returns canonical profiles + log."""
    raw_records, source_log = run_detect_and_extract(sources_dir)
    normalized_records = [normalize_record(r) for r in raw_records]

    blocks = blocking.build_blocks(normalized_records)
    clusters = match.resolve_clusters(normalized_records, blocks)

    profiles = []
    for cluster in clusters:
        cluster_records = [normalized_records[i] for i in cluster["record_indices"]]
        profile = merge.merge_cluster(cluster_records)
        profile["overall_confidence"] = conf_mod.overall_confidence(profile["_field_confidence_map"])
        profile["_match_confidence"] = cluster["match_confidence"]
        profile["_match_tier"] = cluster["match_tier"]
        profile["_contributing_sources"] = sorted(set(r["_source_type"] for r in cluster_records))
        profiles.append(profile)

    return profiles, source_log


def run_pipeline(sources_dir, config, config_name="default"):
    """
    Full run: canonical build + project + validate for ONE config.
    Returns: { "profiles": [...], "source_log": [...], "errors": {...} }
    """
    profiles, source_log = run_canonical(sources_dir)

    projected_outputs = []
    all_errors = {}
    for p in profiles:
        output, proj_errors = project_mod.project(p, config)
        is_valid, val_errors = validate.validate_output(output, config, proj_errors)
        if not is_valid:
            all_errors[p["candidate_id"]] = val_errors
        projected_outputs.append({
            "candidate_id": p["candidate_id"],
            "output": output,
            "valid": is_valid,
            "errors": val_errors,
        })

    return {
        "config_name": config_name,
        "profiles": projected_outputs,
        "source_log": source_log,
        "candidate_count": len(profiles),
    }
