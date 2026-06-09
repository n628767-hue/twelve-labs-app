"""Atlas Demo — FieldLens workforce intelligence platform."""
import json
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

jobs: dict = {}  # video_id -> job state dict


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/process", methods=["POST"])
def process_video():
    from utils.s3 import upload_video, generate_presigned_url, key_from_uri

    if "video" not in request.files:
        return jsonify({"error": "No video file provided"}), 400

    file = request.files["video"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    video_id = str(uuid.uuid4())
    suffix = Path(file.filename).suffix or ".mp4"
    local_path = UPLOAD_DIR / f"{video_id}{suffix}"
    file.save(str(local_path))

    try:
        s3_uri = upload_video(str(local_path), s3_key=f"videos/{video_id}{suffix}")
        s3_key = key_from_uri(s3_uri)
        video_url = generate_presigned_url(s3_key, expires_in=7200)
    except Exception as e:
        return jsonify({"error": f"S3 upload failed: {e}"}), 500
    finally:
        if local_path.exists():
            local_path.unlink()

    jobs[video_id] = {
        "status": "processing",
        "current_step": 1,
        "steps": {
            "compliance": {"status": "running", "result": None},
            "quality":    {"status": "pending", "result": None},
            "annotation": {"status": "pending", "result": None},
        },
        "evidence_pack": None,
    }

    thread = threading.Thread(
        target=_run_pipeline, args=(video_id, video_url), daemon=True
    )
    thread.start()

    return jsonify({"video_id": video_id, "status": "processing"})


def _run_pipeline(video_id: str, video_url: str) -> None:
    from workloads.compliance import run_compliance_gate
    from workloads.quality import run_quality_score
    from workloads.annotation import run_action_annotation
    from utils.evidence import assemble_evidence_pack

    job = jobs[video_id]
    try:
        compliance = run_compliance_gate(video_url)
        job["steps"]["compliance"] = {"status": "complete", "result": compliance}
        job["steps"]["quality"]["status"] = "running"
        job["current_step"] = 2

        quality = run_quality_score(video_url)
        job["steps"]["quality"] = {"status": "complete", "result": quality}
        job["steps"]["annotation"]["status"] = "running"
        job["current_step"] = 3

        annotation = run_action_annotation(video_url)
        job["steps"]["annotation"] = {"status": "complete", "result": annotation}

        pack = assemble_evidence_pack(video_id, compliance, quality, annotation)
        (UPLOAD_DIR / f"{video_id}_evidence.json").write_text(json.dumps(pack, indent=2))

        job["evidence_pack"] = pack
        job["status"] = "complete"

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)


@app.route("/api/status/<video_id>")
def job_status(video_id):
    if video_id not in jobs:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(jobs[video_id])


@app.route("/api/download/<video_id>")
def download_evidence(video_id):
    pack_path = UPLOAD_DIR / f"{video_id}_evidence.json"
    if not pack_path.exists():
        return jsonify({"error": "Evidence pack not found"}), 404
    return send_file(
        str(pack_path),
        mimetype="application/json",
        as_attachment=True,
        download_name=f"evidence_{video_id}.json",
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
