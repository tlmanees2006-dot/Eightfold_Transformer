"""
validate.py
Design doc Section 4/5 - validates the PROJECTED output against the
requested config-schema before returning it (not the canonical record,
which has its own fixed shape by construction).
"""

TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str) or v is None,
    "string[]": lambda v: isinstance(v, list) or v is None,
    "number": lambda v: isinstance(v, (int, float)) or v is None,
    "object": lambda v: isinstance(v, dict) or v is None,
    "array": lambda v: isinstance(v, list) or v is None,
}


def validate_output(output, config, projection_errors):
    """
    Returns (is_valid: bool, error_list: list[str]).
    A candidate that fails validation is reported with a structured error,
    never silently returned as partial/wrong JSON.
    """
    errors = list(projection_errors)

    for field_spec in config.get("fields", []):
        path = field_spec["path"]
        expected_type = field_spec.get("type")
        required = field_spec.get("required", False)

        if path not in output:
            if required:
                errors.append(f"Validation failed: required field '{path}' absent from output.")
            continue

        value = output[path]
        if expected_type and expected_type in TYPE_CHECKS:
            if not TYPE_CHECKS[expected_type](value):
                errors.append(
                    f"Validation failed: field '{path}' expected type '{expected_type}', "
                    f"got '{type(value).__name__}'."
                )

    return (len(errors) == 0), errors
