"""
cli.py
Thin command-line interface (per design doc Section 4 - I/O surface,
intentionally lower priority but still given clean, narrated output).

Usage:
  python cli.py run --sources sample_inputs/ --config configs/default_config.json --out output/default_output.json
  python cli.py run --sources sample_inputs/ --config configs/custom_config_example.json --out output/custom_output.json
  python cli.py explain --candidate-id cand_xxxx --sources sample_inputs/
  python cli.py list --sources sample_inputs/
"""
import argparse
import json
import time
import sys

from src import pipeline


def cmd_run(args):
    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    t0 = time.time()
    print(f"[1/4] Scanning sources in '{args.sources}' ...")
    raw_records, source_log = pipeline.run_detect_and_extract(args.sources)
    parsed = [l for l in source_log if l["status"] == "parsed"]
    skipped = [l for l in source_log if l["status"] != "parsed"]
    for l in parsed:
        print(f"      parsed  {l['file']}  ({l['type']}, {l['records_found']} record(s))")
    for l in skipped:
        print(f"      SKIPPED {l['file']}  ({l.get('reason')})")
    print(f"[2/4] Extracted {len(raw_records)} raw candidate records across {len(parsed)} source(s)")

    result = pipeline.run_pipeline(args.sources, config, config_name=args.config)
    print(f"[3/4] Blocked & matched -> resolved {result['candidate_count']} unique candidate(s)")

    low_conf = [p for p in result["profiles"]
                if "no_stable_identifier" in p["output"].get("data_quality_flags", [])]
    for lc in low_conf:
        print(f"      \u26a0 low-confidence identity (no stable identifier): "
              f"{lc['output'].get('name') or lc['output'].get('full_name') or lc['candidate_id']}")

    import os
    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result["profiles"], f, indent=2)

    invalid = [p for p in result["profiles"] if not p["valid"]]
    print(f"[4/4] Projected output -> {args.out}  "
          f"(schema: {args.config}, {result['candidate_count']} records, "
          f"{len(invalid)} validation issue(s))")
    if invalid:
        for inv in invalid:
            print(f"      INVALID {inv['candidate_id']}: {inv['errors']}")

    print(f"\nDone in {time.time() - t0:.2f}s.")


def cmd_explain(args):
    profiles, _ = pipeline.run_canonical(args.sources)
    match = next((p for p in profiles if p["candidate_id"] == args.candidate_id), None)
    if not match:
        print(f"No candidate found with id '{args.candidate_id}'. Use 'list' to see available IDs.")
        sys.exit(1)

    print(f"=== Explain: {match['full_name']} ({match['candidate_id']}) ===")
    print(f"Contributing sources: {', '.join(match['_contributing_sources'])}")
    print(f"Match tier: {match['_match_tier']}  |  Match confidence: {match['_match_confidence']}")
    print(f"Overall confidence: {match['overall_confidence']}")
    print(f"Data quality flags: {match['data_quality_flags'] or 'none'}")
    print("\nField-by-field provenance:")
    for p in match["provenance"]:
        print(f"  - {p['field']:<16} <- {p['source']:<10} ({p['method']}, confidence={p['confidence']})")


def cmd_list(args):
    profiles, _ = pipeline.run_canonical(args.sources)
    print(f"{'candidate_id':<22} {'name':<18} {'sources':<28} confidence")
    for p in profiles:
        print(f"{p['candidate_id']:<22} {(p['full_name'] or '-'):<18} "
              f"{','.join(p['_contributing_sources']):<28} {p['overall_confidence']}")


def main():
    parser = argparse.ArgumentParser(description="Eightfold Candidate Profile Transformer")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run the pipeline end-to-end")
    p_run.add_argument("--sources", required=True, help="Path to folder of source files")
    p_run.add_argument("--config", required=True, help="Path to a runtime output config JSON")
    p_run.add_argument("--out", required=True, help="Path to write output JSON")
    p_run.set_defaults(func=cmd_run)

    p_explain = sub.add_parser("explain", help="Explain how one candidate's profile was built")
    p_explain.add_argument("--sources", required=True)
    p_explain.add_argument("--candidate-id", required=True)
    p_explain.set_defaults(func=cmd_explain)

    p_list = sub.add_parser("list", help="List all resolved candidates and their IDs")
    p_list.add_argument("--sources", required=True)
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
