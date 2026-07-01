"""
extractors/csv_extractor.py
Extracts raw candidate records from the recruiter CSV export.
Output: list of raw dicts (untouched values, normalization happens later).
"""
import csv


def extract(path):
    records = []
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append({
                    "_source_type": "csv",
                    "_source_file": path,
                    "raw_name": row.get("name"),
                    "raw_email": row.get("email"),
                    "raw_phone": row.get("phone"),
                    "raw_company": row.get("current_company"),
                    "raw_title": row.get("title"),
                    "raw_skills": [],  # CSV export format has no skills column
                })
    except Exception as e:
        # Garbage/unreadable source -> log and return empty, never crash the run.
        print(f"[WARN] Failed to parse CSV source '{path}': {e}")
        return []
    return records
