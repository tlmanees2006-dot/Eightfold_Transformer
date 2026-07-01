"""
detect.py
Detects the type of a source file by sniffing its content, not trusting
the file extension alone (Design doc Section 1 - Detect stage).
"""
import os
import json


SOURCE_CSV = "csv"
SOURCE_ATS_JSON = "ats_json"
SOURCE_RESUME = "resume"
SOURCE_NOTES = "notes"
SOURCE_UNKNOWN = "unknown"


def detect_source_type(path):
    """
    Returns one of SOURCE_CSV, SOURCE_ATS_JSON, SOURCE_RESUME, SOURCE_NOTES, SOURCE_UNKNOWN.
    Never raises - a garbled/unreadable file simply returns SOURCE_UNKNOWN so the
    pipeline can skip it gracefully (robustness requirement).
    """
    try:
        if not os.path.isfile(path):
            return SOURCE_UNKNOWN

        ext = os.path.splitext(path)[1].lower()

        if ext == ".pdf":
            return SOURCE_RESUME
        if ext == ".docx":
            return SOURCE_RESUME

        if ext == ".json":
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "candidates" in data:
                    return SOURCE_ATS_JSON
                return SOURCE_ATS_JSON  # treat any structured JSON blob as ATS-type
            except Exception:
                return SOURCE_UNKNOWN  # malformed JSON -> garbage source, skip gracefully

        if ext == ".csv":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                first_line = f.readline()
            if "," in first_line:
                return SOURCE_CSV
            return SOURCE_UNKNOWN

        if ext == ".txt":
            # Heuristic: recruiter notes are free text, often with "---" entry separators
            # or sentence-like structure rather than column headers.
            return SOURCE_NOTES

        return SOURCE_UNKNOWN
    except Exception:
        return SOURCE_UNKNOWN
