# Eightfold Candidate Profile Transformer

Ingests candidate data from multiple structured and unstructured sources and
produces one clean, canonical, trust-scored JSON profile per candidate —
with every field traceable to its source and method, and a runtime config
layer that reshapes output without touching the core engine.

This implementation follows the Stage 1 design doc exactly:
**Detect → Extract → Normalize → Block → Match → Merge/Confidence → Project → Validate**

## 1. Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Run via CLI (default schema)

```bash
python cli.py run --sources sample_inputs/ --config configs/default_config.json --out output/default_output.json
```

## 3. Run via CLI (custom config — subset, rename, normalize, toggles)

```bash
python cli.py run --sources sample_inputs/ --config configs/custom_config_example.json --out output/custom_output.json
```

The CLI prints a narrated, stage-by-stage run summary (sources scanned,
records extracted, candidates resolved, low-confidence flags) before
writing the output JSON — not a silent script.

## 4. Other CLI commands

```bash
# List all resolved candidates and their IDs
python cli.py list --sources sample_inputs/

# Explain exactly how one candidate's profile was built (full provenance trace)
python cli.py explain --sources sample_inputs/ --candidate-id <id from 'list'>
```

## 5. Run via Web UI (more demo-friendly than the CLI)

```bash
python app.py
```
Then open **http://127.0.0.1:5000**.

**Input sources**: choose "Use sample inputs" (bundled `sample_inputs/`) or
"Upload my own files" — drag/select any mix of CSV, JSON, TXT, PDF, DOCX and
click Upload. The pipeline runs against exactly the files you provide, same
as the CLI's `--sources` flag.

**Output config**: choose a preset (default schema / subset+rename example),
or use "Build my own config" to visually compose a config exercising every
capability from the design doc — add/remove fields, set each field's output
name and its `from` canonical path (subset selection + rename/remap), pick a
per-field `normalize` function, set `required`, toggle confidence/provenance
on or off, and choose the missing-value policy (null / omit / error). "Edit
raw JSON" is also available for full manual control.

Click **Run pipeline**, then expand any candidate card to see the full
projected JSON, or click **"Explain this profile"** for a field-by-field
provenance trace and the match tier that linked that candidate's sources.

The UI is a thin presentation layer (`app.py` + `templates/index.html`) —
it calls the exact same `src/pipeline.py` engine the CLI uses. No pipeline
logic lives in the UI layer, by design.

## 6. Run tests

```bash
pytest tests/ -v
```
13 tests covering: normalization correctness (phone/date/skill variants
converging), match/merge logic on the real sample candidates, robustness
(a deliberately corrupted JSON source file does not crash the run), and a
gold-profile comparison (hand-written expected values for one candidate,
checked field-by-field against actual pipeline output).

## Project structure

```
src/
  detect.py          Source type detection by content sniffing
  extractors/         One extractor per source type (CSV, ATS JSON, resume, notes)
  normalize.py        Phone/date/country/skill/name/email normalization
  skills_dictionary.json  External, config-driven skill canonicalization map
  blocking.py          Cheap-key candidate grouping before matching (scale)
  match.py             Tiered match-key resolution (email > phone > fuzzy)
  merge.py              Field-winner selection, provenance, confidence inputs
  confidence.py        Confidence formula (field-level + overall)
  project.py            Generic path-resolver for runtime config projection
  validate.py           Output validation against the requested config-schema
  pipeline.py            Orchestrates all stages end-to-end
cli.py                 Command-line interface
app.py / templates/    Web UI (same engine, presentation layer only)
configs/                Default + example custom runtime configs
sample_inputs/          Self-constructed sample data (see note below)
tests/                  pytest suite
output/                  Generated JSON output lands here
MANEES KUMAR T_maneeskumart.cse2023@citchennai.net_Eightfold (2).pdf               Stage 1 technical design document
```

## Sample input data

No sample files were provided with the assignment, so the inputs in
`sample_inputs/` were self-constructed to deliberately exercise every
required behavior: a 4-source merge (Ananya Sharma: CSV + ATS JSON +
resume + notes), a near-duplicate-email match (Rohit Verma), a candidate
with no email/phone at all (Devansh Rao — tests the "no stable identifier"
edge case), a candidate with a missing structured field (Priya Nair's
blank phone), and notes-only / resume-only single-source candidates.

GitHub and LinkedIn sources were deliberately descoped (see Limitations).

## Key design decisions

- **Blocking before matching** (`blocking.py`): candidates are grouped by
  cheap keys (normalized email/phone/name) before any pairwise comparison,
  avoiding O(n²) cost — the standard entity-resolution technique that lets
  this scale to thousands of candidates.
- **Tiered match keys, never on name alone**: email > phone > fuzzy-email
  > fuzzy-name+employer. A record is never auto-merged with another purely
  on name similarity — false merges are worse than two honest, separate
  profiles.
- **Skills are unioned, not overridden**: agreement across sources raises
  a skill's confidence rather than one source "winning."
- **Generic path-resolver for config projection** (`project.py`): the
  runtime config's `from` field is interpreted as a generic path
  (`skills[].name`, `emails[0]`, etc.) against the canonical record, so new
  configs require zero code changes — no per-field hardcoding.
- **`required: true` always overrides `on_missing`**: a required field that's
  absent always produces a scoped validation error for that one candidate,
  without halting the rest of the batch.
- **`data_quality_flags[]`**: makes weak records (no stable identifier,
  single-source, missing fields) visibly weak, not just numerically
  lower-scored — directly serves the "wrong-but-confident is worse than
  honestly-empty" principle.

## Edge cases handled (see tests/test_edge_cases.py and test_match_merge.py)

1. No email/phone at all → name-hash fallback ID, flagged, capped confidence.
2. Near-duplicate identity (slightly different email) → fuzzy-match tier,
   logged with its own match_confidence for auditability.
3. Semantically-equal but textually different values (e.g. "Full Stack
   Developer" vs "Full Stack Consultant") → similarity-collapsed, not
   treated as a false conflict.
4. Missing structured field (blank phone) → left null, never fabricated.
5. Garbage/corrupt source file → logged and skipped, rest of the batch
   processes normally (see `test_pipeline_survives_garbage_source_file`).

## Deliberately descoped (stated honestly, not hidden)

- Live GitHub/LinkedIn API integration — kept the pipeline fully
  deterministic and offline-runnable for reproducible sample runs.
- ML-based fuzzy matching — used explainable string-similarity (edit
  distance, sequence matching) instead of a trained classifier, prioritizing
  defensibility over marginal accuracy gains.
- A review-queue UI for low-confidence matches — flagged via
  `data_quality_flags` and confidence scores, but no operational review
  workflow built.
- Non-Latin name transliteration.

## Demo video 

[https://drive.google.com/drive/folders/1SJOsFdhc6t5CASsX0R9bjt0AgD6bVSDY?usp=sharing] --  With VoiceOver
