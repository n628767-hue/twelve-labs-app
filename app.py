"""Atlas Demo — FieldLens workforce intelligence platform."""
import json
import os
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


@app.errorhandler(413)
def request_too_large(e):
    return jsonify({"error": "File too large"}), 413


@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": f"Internal server error: {e}"}), 500


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/upload-url", methods=["POST"])
def get_upload_url():
    """Return a presigned S3 PUT URL so the browser can upload directly to S3."""
    import boto3
    data = request.get_json(silent=True) or {}
    filename = data.get("filename", "video.mp4")
    suffix = Path(filename).suffix or ".mp4"
    video_id = str(uuid.uuid4())
    s3_key = f"videos/{video_id}{suffix}"

    bucket = os.environ.get("S3_BUCKET")
    region = os.environ.get("AWS_REGION", "us-east-1")

    try:
        s3 = boto3.client("s3", region_name=region)
        upload_url = s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": s3_key, "ContentType": "video/*"},
            ExpiresIn=3600,
        )
    except Exception as e:
        return jsonify({"error": f"Could not generate upload URL: {e}"}), 500

    return jsonify({"video_id": video_id, "upload_url": upload_url, "s3_key": s3_key})


@app.route("/api/process", methods=["POST"])
def process_video():
    """Start the pipeline for a video already uploaded to S3."""
    data = request.get_json(silent=True) or {}
    video_id = data.get("video_id")
    s3_key = data.get("s3_key")

    if not video_id or not s3_key:
        return jsonify({"error": "video_id and s3_key are required"}), 400

    from utils.s3 import generate_presigned_url
    try:
        video_url = generate_presigned_url(s3_key, expires_in=7200)
    except Exception as e:
        return jsonify({"error": f"Could not generate presigned URL: {e}"}), 500

    jobs[video_id] = {
        "status": "processing",
        "current_step": 1,
        "steps": {
            "compliance": {"status": "pending", "result": None},
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
        job["steps"]["compliance"]["status"] = "running"
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
