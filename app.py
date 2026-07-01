"""
app.py
A minimal, user-friendly web UI on top of the SAME pipeline the CLI uses
(src/pipeline.py). This is purely a presentation layer - no pipeline logic
lives here, satisfying the "thin I/O surface" requirement while being more
approachable than a terminal for a non-technical reviewer.

Supports two input modes, matching the CLI's --sources flag:
  1. "Use sample inputs"  -> runs against sample_inputs/ (bundled with repo)
  2. "Upload your own"    -> user uploads CSV/JSON/TXT/PDF/DOCX files through
                             the browser, which are written to uploads/<session_id>/
                             and the pipeline runs against THAT folder instead.

Run:
    python app.py
Then open http://127.0.0.1:5000
"""
import json
import os
import shutil
import uuid
from flask import Flask, render_template, request, jsonify, send_file, session

from src import pipeline

app = Flask(__name__)
app.secret_key = "eightfold-demo-secret-key"  # fine for a local demo tool, not production

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_SOURCES = os.path.join(BASE_DIR, "sample_inputs")
DEFAULT_CONFIG_PATH = os.path.join(BASE_DIR, "configs", "default_config.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
UPLOADS_ROOT = os.path.join(BASE_DIR, "uploads")

ALLOWED_EXTENSIONS = {".csv", ".json", ".txt", ".pdf", ".docx"}


def _load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_session_upload_dir(create=False):
    if "upload_session_id" not in session:
        session["upload_session_id"] = uuid.uuid4().hex
    path = os.path.join(UPLOADS_ROOT, session["upload_session_id"])
    if create:
        os.makedirs(path, exist_ok=True)
    return path


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """
    Accepts one or more files via multipart/form-data (field name 'files').
    Replaces this browser session's uploaded source set each time (so
    re-uploading starts fresh rather than accumulating stale files).
    Returns the list of accepted/rejected filenames.
    """
    upload_dir = _get_session_upload_dir(create=True)
    # clear previous uploads for this session before saving the new batch
    shutil.rmtree(upload_dir, ignore_errors=True)
    os.makedirs(upload_dir, exist_ok=True)

    accepted, rejected = [], []
    files = request.files.getlist("files")
    for f in files:
        if not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            rejected.append(f.filename)
            continue
        safe_name = os.path.basename(f.filename)
        f.save(os.path.join(upload_dir, safe_name))
        accepted.append(safe_name)

    return jsonify({"accepted": accepted, "rejected": rejected, "upload_dir_has_files": len(accepted) > 0})


@app.route("/api/run", methods=["POST"])
def api_run():
    """
    Accepts JSON body: { "config": {...}, "source_mode": "sample"|"uploaded" }
    "sample" runs against the bundled sample_inputs/ folder.
    "uploaded" runs against whatever this browser session uploaded via /api/upload.
    """
    body = request.get_json(force=True) or {}
    config = body.get("config") or _load_config(DEFAULT_CONFIG_PATH)
    source_mode = body.get("source_mode", "sample")

    if source_mode == "uploaded":
        sources_dir = _get_session_upload_dir(create=True)
        if not os.listdir(sources_dir):
            return jsonify({"error": "No uploaded files found for this session. "
                                      "Upload files first, or switch to 'Use sample inputs'."}), 400
    else:
        sources_dir = SAMPLE_SOURCES

    result = pipeline.run_pipeline(sources_dir, config, config_name="ui_run")

    return jsonify({
        "source_log": result["source_log"],
        "candidate_count": result["candidate_count"],
        "profiles": result["profiles"],
        "sources_dir_used": "sample_inputs/" if source_mode == "sample" else "your uploaded files",
    })


@app.route("/api/explain/<candidate_id>")
def api_explain(candidate_id):
    source_mode = request.args.get("source_mode", "sample")
    if source_mode == "uploaded":
        sources_dir = _get_session_upload_dir(create=True)
    else:
        sources_dir = SAMPLE_SOURCES

    profiles, _ = pipeline.run_canonical(sources_dir)
    match = next((p for p in profiles if p["candidate_id"] == candidate_id), None)
    if not match:
        return jsonify({"error": "not found"}), 404
    match = dict(match)
    match.pop("_field_confidence_map", None)
    return jsonify(match)


@app.route("/api/default_config")
def api_default_config():
    return jsonify(_load_config(DEFAULT_CONFIG_PATH))


@app.route("/api/download/<filename>")
def api_download(filename):
    path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.isfile(path):
        return jsonify({"error": "not found"}), 404
    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(UPLOADS_ROOT, exist_ok=True)
    app.run(debug=True, port=5000)
