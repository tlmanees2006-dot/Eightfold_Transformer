import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import pipeline

SAMPLES = os.path.join(os.path.dirname(__file__), "..", "sample_inputs")


def _profiles():
    profiles, _ = pipeline.run_canonical(SAMPLES)
    return {p["full_name"]: p for p in profiles}


def test_candidate_count_is_seven():
    profiles = _profiles()
    assert len(profiles) == 7, f"Expected 7 unique candidates, got {len(profiles)}"


def test_rohit_near_duplicate_emails_merge_into_one():
    profiles = _profiles()
    assert "Rohit Verma" in profiles
    rohit = profiles["Rohit Verma"]
    assert set(rohit["_contributing_sources"]) == {"csv", "ats_json"}


def test_devansh_never_merged_on_name_alone_and_flagged_low_confidence():
    profiles = _profiles()
    devansh = profiles["Devansh Rao"]
    assert "no_stable_identifier" in devansh["data_quality_flags"]
    assert devansh["overall_confidence"] < 0.5


def test_priya_missing_phone_handled_gracefully():
    profiles = _profiles()
    priya = profiles["Priya Nair"]
    assert priya["phones"] == []
    assert "no_phone_present" in priya["data_quality_flags"]


def test_ananya_four_source_merge():
    profiles = _profiles()
    ananya = profiles["Ananya Sharma"]
    assert set(ananya["_contributing_sources"]) == {"csv", "ats_json", "resume", "notes"}
    assert ananya["overall_confidence"] > 0.6


if __name__ == "__main__":
    test_candidate_count_is_seven()
    test_rohit_near_duplicate_emails_merge_into_one()
    test_devansh_never_merged_on_name_alone_and_flagged_low_confidence()
    test_priya_missing_phone_handled_gracefully()
    test_ananya_four_source_merge()
    print("All match/merge tests passed.")
