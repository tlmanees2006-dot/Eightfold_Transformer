"""
confidence.py
Design doc Section 3 - confidence formula:

  field_confidence = 0.5*source_reliability + 0.4*cross_source_agreement_ratio + 0.1*recency

  overall_confidence = importance-weighted mean of field confidences
  (identity fields weighted ~2x skills/headline)
"""

SOURCE_RELIABILITY = {
    "csv": 0.9,
    "ats_json": 0.9,
    "resume": 0.85,
    "notes": 0.6,
}

FIELD_IMPORTANCE = {
    "full_name": 1.5,
    "emails": 2.0,
    "phones": 2.0,
    "location": 1.0,
    "headline": 0.7,
    "years_experience": 1.0,
    "skills": 0.8,
    "experience": 1.2,
    "education": 1.0,
}


def field_confidence(value_sources, winning_source_type, is_most_recent=True):
    """
    value_sources: list of source_type strings that contributed *some* value
                    for this field (used for agreement ratio).
    winning_source_type: source_type of the value that was actually chosen.
    is_most_recent: whether the winning source is the most recent one available.
    """
    if not value_sources:
        return 0.0

    reliability = SOURCE_RELIABILITY.get(winning_source_type, 0.5)

    # agreement ratio: how many sources' values match the chosen value family
    # (approximated upstream by merge.py passing in the count of agreeing sources)
    agreeing = value_sources.count(winning_source_type) if winning_source_type in value_sources else 1
    agreement_ratio = agreeing / len(value_sources)

    recency = 1.0 if is_most_recent else 0.6

    score = (0.5 * reliability) + (0.4 * agreement_ratio) + (0.1 * recency)
    return round(min(score, 1.0), 3)


def overall_confidence(field_confidence_map):
    """
    field_confidence_map: { field_name: confidence_float }
    Returns importance-weighted mean.
    """
    if not field_confidence_map:
        return 0.0
    total_weight = 0.0
    total_score = 0.0
    for field, conf in field_confidence_map.items():
        if conf is None:
            continue
        weight = FIELD_IMPORTANCE.get(field, 0.8)
        total_weight += weight
        total_score += weight * conf
    if total_weight == 0:
        return 0.0
    return round(total_score / total_weight, 3)
