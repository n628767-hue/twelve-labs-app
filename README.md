# FieldLens Atlas

Egocentric workplace video processed through three AI workloads: compliance screening, training-data quality scoring, and action annotation. Runs as a local Flask app for development and as an AWS Lambda + Step Functions pipeline for production.

> **Sales engineers:** see [DEMO_GUIDE.md](DEMO_GUIDE.md) for setup, demo script, and handoff instructions.

---

## Features

- **Compliance gate** — screens six risk categories (minors, PII, unsafe acts, etc.) and returns a PASS / REVIEW REQUIRED / BLOCK disposition with per-category evidence
- **Quality score** — rates five training-data quality dimensions on a 1–5 scale and returns a PASS / REVIEW / REJECT verdict
- **Action annotation** — segments video into time-coded atomic actions with structured metadata (verb, noun, hand, task type, confidence); uses Pegasus 1.5 + Marengo 3.0 in dual-model mode when configured
- **Real-time UI** — results render card by card as each workload completes; no waiting for the full pipeline
- **Evidence pack** — all three outputs assembled into a single downloadable JSON artifact

---

## Prerequisites

- Python 3.9+
- AWS account with S3 access
- TwelveLabs API key

---

## Installation

```bash
git clone https://github.com/n628767-hue/twelve-labs-app.git
cd twelve-labs-app
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your credentials (see [Configuration](#configuration) below).

---

## Usage

### Local development

```bash
# macOS: port 5000 is reserved by AirPlay Receiver
flask run --port 5001
```

Open `http://localhost:5001`, upload a video, and click **Run Full Intelligence Pipeline**. The three workloads run in the background and results populate in real time.

### AWS deployment

Requires the [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) and Python 3.12.

```bash
# 1. Enable S3 CORS so the browser can upload directly to S3
aws s3api put-bucket-cors --bucket YOUR_BUCKET --cors-configuration '{
  "CORSRules": [{
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["PUT", "GET", "HEAD"],
    "AllowedOrigins": ["*"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }]
}'

# 2. Store the API key in SSM before deploying (use --type String, not SecureString)
aws ssm put-parameter \
  --name /atlas-demo/TWELVELABS_API_KEY \
  --value "tlk_..." \
  --type String --region us-east-1

sam build && sam deploy
```

To trigger the pipeline after deploying:

```bash
aws s3 presign s3://YOUR_BUCKET/videos/YOUR_VIDEO.mp4 --expires-in 7200

aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:us-east-1:ACCOUNT:stateMachine:VideoProcessingStateMachine-XXXXX \
  --input '{"video_url":"https://...","video_id":"your-uuid"}'
```

---

## Configuration

| Variable | Required | Description |
|---|---|---|
| `TWELVELABS_API_KEY` | Yes | TwelveLabs API key |
| `S3_BUCKET` | Yes | S3 bucket for video storage |
| `AWS_ACCESS_KEY_ID` | Yes* | AWS access key (*or use `~/.aws/credentials` / IAM role) |
| `AWS_SECRET_ACCESS_KEY` | Yes* | AWS secret key |
| `AWS_REGION` | No | AWS region (default: `us-east-1`) |
| `MARENGO_INDEX_ID` | No | TwelveLabs index for Workload 3 dual-model path |
| `MARENGO_VIDEO_ID` | No | TwelveLabs video ID within that index |

---

## Architecture

### Local mode

```
Browser → Flask (app.py)
  ├── POST /api/upload-url → returns presigned S3 PUT URL
  ├── Browser PUTs video directly to S3 (bypasses Flask)
  ├── POST /api/process {video_id, s3_key} → starts background thread
  └── background thread runs three workloads sequentially
       ├── Workload 1 → TwelveLabs Pegasus 1.5 (sync analyze)
       ├── Workload 2 → TwelveLabs Pegasus 1.5 (sync analyze)
       └── Workload 3 → TwelveLabs Pegasus 1.5 (async TBM) + Marengo 3.0 (optional)

Browser polls /api/status every 3s — cards render as each workload completes.
```

### AWS mode

```
S3 presigned URL + video_id
  └── Step Functions: VideoProcessingStateMachine (STANDARD)
       ├── ComplianceGate   → Lambda 120s  → workloads/compliance.py
       ├── QualityScore     → Lambda 120s  → workloads/quality.py
       └── ActionAnnotation → Lambda 660s  → workloads/annotation.py
```

`video_url` and `video_id` flow through every state unchanged via `ResultPath`.

---

## Project Structure

```
app.py               Flask app — local development entry point
lambda_handler.py    Lambda entry points for the three workloads
template.yaml        SAM template — Lambda functions + Step Functions state machine
samconfig.toml       SAM deploy defaults
workloads/
  compliance.py      Workload 1 — compliance gate prompt + schema
  quality.py         Workload 2 — quality score prompt + schema
  annotation.py      Workload 3 — dual-model annotation pipeline
utils/
  tl_client.py       TwelveLabs client singleton
  s3.py              S3 upload + presigned URL helpers
  evidence.py        Evidence pack assembly
templates/
  index.html         Single-page UI
```
