"""Atlas Demo — FieldLens workforce intelligence platform."""
import json
import os
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


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/process", methods=["POST"])
def process_video():
    from utils.s3 import upload_video, generate_presigned_url, key_from_uri
    from workloads.compliance import run_compliance_gate
    from workloads.quality import run_quality_score
    from workloads.annotation import run_action_annotation
    from utils.evidence import assemble_evidence_pack

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

        compliance = run_compliance_gate(video_url)
        quality = run_quality_score(video_url)
        annotation = run_action_annotation(video_url)
        pack = assemble_evidence_pack(video_id, compliance, quality, annotation)

        pack_path = UPLOAD_DIR / f"{video_id}_evidence.json"
        pack_path.write_text(json.dumps(pack, indent=2))

        return jsonify({"video_id": video_id, "evidence_pack": pack})

    finally:
        if local_path.exists():
            local_path.unlink()


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
