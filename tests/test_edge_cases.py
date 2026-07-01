import sys, os, json, shutil, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import pipeline

SAMPLES = os.path.join(os.path.dirname(__file__), "..", "sample_inputs")


def test_pipeline_survives_garbage_source_file():
    tmpdir = tempfile.mkdtemp()
    try:
        shutil.copytree(SAMPLES, os.path.join(tmpdir, "sources"))
        broken_path = os.path.join(tmpdir, "sources", "broken.json")
        with open(broken_path, "w") as f:
            f.write("{ this is not valid json !!!")

        profiles, log = pipeline.run_canonical(os.path.join(tmpdir, "sources"))

        skipped = [l for l in log if l["status"] == "skipped" and "broken.json" in l["file"]]
        assert len(skipped) == 1, "Broken JSON file should be logged as skipped, not crash the run"
        assert len(profiles) == 7, "All other candidates should still be processed normally"
    finally:
        shutil.rmtree(tmpdir)


def test_missing_sources_dir_does_not_crash():
    profiles, log = pipeline.run_canonical(os.path.join(tempfile.mkdtemp(), "does_not_exist"))
    assert profiles == []
    assert log == []


GOLD_ANANYA = {
    "full_name": "Ananya Sharma",
    "emails": ["ananya.sharma@gmail.com"],
    "phones": ["+919876543210"],
    "years_experience": 6,
}


def test_gold_profile_comparison_ananya():
    """Gold-profile test: hand-written expected values for Ananya, compared
    field-by-field against actual pipeline output (per design doc Section 5
    optional testing requirement)."""
    profiles, _ = pipeline.run_canonical(SAMPLES)
    ananya = next(p for p in profiles if p["full_name"] == "Ananya Sharma")
    for field, expected in GOLD_ANANYA.items():
        actual = ananya[field]
        assert actual == expected, f"Gold mismatch on '{field}': expected {expected}, got {actual}"


if __name__ == "__main__":
    test_pipeline_survives_garbage_source_file()
    test_missing_sources_dir_does_not_crash()
    test_gold_profile_comparison_ananya()
    print("All edge case tests passed.")
