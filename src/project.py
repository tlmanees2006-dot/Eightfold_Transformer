"""
project.py
Design doc Section 4 - Runtime Custom-Output Config (Projection + Validation).

Canonical record is NEVER mutated here - projection always operates on a
deep copy, and produces an entirely separate output dict. The resolver is
GENERIC: it interprets a 'from' path like 'emails[0]' or 'skills[].name'
against the canonical record, so adding new fields to a config requires
ZERO code changes here.
"""
import copy
import re
from src.normalize import normalize_phone, normalize_skill

NORMALIZER_REGISTRY = {
    "E164": lambda v: normalize_phone(v) if v else v,
    "canonical": lambda v: normalize_skill(v) if isinstance(v, str) else v,
    "string[]": lambda v: v,
}


def _resolve_path(record, path):
    """
    Resolves a path like 'emails[0]', 'skills[].name', 'experience[0].company'
    against `record`. Supports:
      - plain dotted access: 'location.city'
      - fixed index: 'emails[0]'
      - wildcard array projection: 'skills[].name' -> list of names
    Returns the resolved value, or None if not found.
    """
    tokens = re.findall(r"[^.\[\]]+|\[\d*\]", path)
    current = record

    for i, tok in enumerate(tokens):
        if tok == "[]":
            remaining = ".".join(_reconstruct(tokens[i + 1:]))
            if not isinstance(current, list):
                return None
            results = []
            for item in current:
                val = _resolve_path(item, remaining) if remaining else item
                if val is not None:
                    results.append(val)
            return results
        elif re.match(r"^\[\d+\]$", tok):
            idx = int(tok[1:-1])
            if not isinstance(current, list) or idx >= len(current):
                return None
            current = current[idx]
        else:
            if isinstance(current, dict):
                current = current.get(tok)
            else:
                return None
        if current is None:
            return None
    return current


def _reconstruct(tokens):
    out = []
    for t in tokens:
        if t.startswith("["):
            out[-1] = out[-1] + t if out else t
        else:
            out.append(t)
    return out


def project(canonical_record, config):
    """
    Applies a runtime config to a canonical record (never mutating the
    original). Returns (output_dict, errors_list).
    """
    record = copy.deepcopy(canonical_record)
    record.pop("_field_confidence_map", None)

    output = {}
    errors = []
    on_missing = config.get("on_missing", "null")
    include_confidence = config.get("include_confidence", True)
    include_provenance = config.get("include_provenance", True)

    field_conf_map = canonical_record.get("_field_confidence_map", {})

    for field_spec in config.get("fields", []):
        out_path = field_spec["path"]
        from_path = field_spec.get("from", out_path)
        required = field_spec.get("required", False)
        normalize_fn_name = field_spec.get("normalize")

        value = _resolve_path(record, from_path)

        if normalize_fn_name and value is not None:
            fn = NORMALIZER_REGISTRY.get(normalize_fn_name)
            if fn:
                if isinstance(value, list):
                    value = [fn(v) for v in value]
                else:
                    value = fn(value)

        if value is None or value == [] or value == "":
            if required:
                # required:true ALWAYS overrides on_missing - design doc Section 4 rule
                errors.append(f"Required field '{out_path}' (from '{from_path}') is missing.")
                continue
            if on_missing == "null":
                output[out_path] = None
            elif on_missing == "omit":
                continue
            elif on_missing == "error":
                errors.append(f"Field '{out_path}' is missing and on_missing policy is 'error'.")
                continue
        else:
            output[out_path] = value

    if include_confidence:
        output["confidence"] = field_conf_map

    if include_provenance:
        output["provenance"] = canonical_record.get("provenance", [])

    output["data_quality_flags"] = canonical_record.get("data_quality_flags", [])

    return output, errors
