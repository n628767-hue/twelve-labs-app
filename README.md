# FieldLens Atlas

Three AI workloads on egocentric workplace video — compliance screening, training-data quality scoring, and action annotation — delivered as a local Flask demo and a production-grade Lambda + Step Functions pipeline.

---

## 1. Quick Start

**Time to first working demo: ~20 minutes**

### What you need

- Python 3.9+
- A TwelveLabs API key (get one at platform.twelvelabs.io)
- AWS credentials with S3 access and an S3 bucket to use
- A short egocentric/POV workplace video to demo with (MP4, MOV, or AVI)

### Steps

```bash
# 1. Clone and install
git clone https://github.com/n628767-hue/twelve-labs-app.git
cd twelve-labs-app
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
```

Open `.env` and fill in three values — that's all you need for local demo:

```
TWELVELABS_API_KEY=tlk_...
S3_BUCKET=your-bucket-name
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

```bash
# 3. Run (macOS: port 5000 is taken by AirPlay — use 5001)
flask run --port 5001
```

Open `http://localhost:5001`, drop in a video, click **Run Full Intelligence Pipeline**.

### Confirm it's working

The step counter in the UI should immediately show "Compliance Gate running… Step 1 of 3" with a pulsing dot on the first card. Results populate card by card as each workload finishes. If you see an error, check that your S3 bucket exists and your API key is valid.

---

## 2. Adapting for a New Customer

The three workloads are prompt-driven. Swapping in a customer's use case means editing prompts and field definitions — no infrastructure changes required.

### Change what gets screened (Workload 1)

**File:** `workloads/compliance.py`

Edit the `PROMPT` string and the `SCHEMA` dict. The categories, severity levels, and disposition logic are all in the prompt. For a customer in healthcare, swap "competitor_ip" for "patient_data_visible". For construction, add "fall_hazard_proximity".

### Change what quality means (Workload 2)

**File:** `workloads/quality.py`

Edit the `PROMPT` string and `SCHEMA`. The five dimensions and their 1–5 scales are defined in the prompt. For a customer focused on training data for surgical robotics, "action_visibility" and "lighting_adequacy" matter more than "audio_intelligibility" — reweight accordingly.

### Change what actions get annotated (Workload 3)

**File:** `workloads/annotation.py`

Edit `SEGMENT_DESCRIPTION` and the `FIELDS` list. These control what Pegasus segments and what metadata it extracts per segment. The enum values on `task_type` and `hand` can be extended or replaced. For a customer annotating customer service interactions rather than physical tasks, `hand` becomes irrelevant — remove it.

### Other things to change per customer

| What | Where |
|---|---|
| App name / branding | `templates/index.html` — the `<title>` and `<header>` section |
| S3 bucket | `.env` → `S3_BUCKET` |
| AWS region | `.env` → `AWS_REGION` (default: `us-east-1`) |
| Evidence pack fields | `utils/evidence.py` → `assemble_evidence_pack()` |

---

## 3. Running the Demo

### Before you start

- Have a 1–5 minute egocentric/POV workplace video ready. The demo lands better with real customer footage, but any first-person task video works.
- Make sure the Flask app is running (`flask run --port 5001`) and you can reach `http://localhost:5001`.

### Demo flow

**Step 1 — Upload**
Drop the video onto the upload zone and click **Run Full Intelligence Pipeline**. The video uploads to S3 in the background and processing starts immediately.

**Step 2 — Show real-time progress**
Point to the step counter: "You can see it's on Step 1 of 3 — Compliance Gate is running right now." The dot on Card 1 pulses blue while it's active and turns green when it finishes. This is a good moment to explain what compliance screening is doing.

**Step 3 — Compliance card populates (~30–60 seconds)**
Walk through the six categories and the PASS / REVIEW REQUIRED / BLOCK disposition. If any categories are FLAGGED, show the evidence text and timestamp. Key message: *this is structured output a reviewer can act on, not a summary paragraph.*

**Step 4 — Quality card populates (~30–60 seconds)**
Show the five 1–5 dimension scores and the overall PASS / REVIEW / REJECT verdict. Key message: *this is what an AI training data pipeline needs before ingestion — objective quality gates, not manual spot-checking.*

**Step 5 — Annotation card populates (2–8 minutes)**
This one takes longer because it uses async time-based metadata extraction. Show the time-coded action segments with verb/noun/hand labels. Key message: *this is structured ground truth for training action recognition models — produced automatically from raw egocentric video.*

**Step 6 — Download the evidence pack**
Click **Download JSON**. Open it and show the structure: all three workload outputs in a single audit-ready document with a reviewer summary. Key message: *one API call, three AI workloads, one evidence artifact.*

### Talking points that land well

- "The same code runs locally for prototyping and in Lambda for production — no rewrite."
- "The prompts are the product. We tuned them for your compliance categories; you own them."
- "The annotation workload uses both Pegasus and Marengo — any segment only one model detects gets flagged LOW confidence and routed to human review automatically."

---

## 4. Handing Off to Another SE

### Share the repo and credentials

The next SE needs:
1. Access to this repo
2. A TwelveLabs API key (create a new one — don't share yours)
3. AWS credentials with S3 read/write on the bucket used in `.env`

### Set up the TwelveLabs MCP plugin in Claude Code

This gives the next SE the same ability to list indexes, search videos, and run analyses directly from Claude Code conversations — no API docs needed.

```bash
# Run this inside the project directory
claude plugin install twelvelabs@twelvelabs-plugins
```

Then create `.claude/settings.json` in the project root:

```json
{
  "enabledPlugins": {
    "twelvelabs@twelvelabs-plugins": true
  }
}
```

The plugin picks up `TWELVELABS_API_KEY` from the environment automatically. With it installed, the SE can ask Claude Code things like "list my indexes", "search for the moment the worker picks up the tool", or "what videos do I have?" and get live results inline.

### For AWS deployment (if handing off a production instance)

The deployed stack lives at `atlas-demo` in `us-east-1`. The TwelveLabs API key is in SSM at `/atlas-demo/TWELVELABS_API_KEY`. To redeploy after changes:

```bash
sam build && sam deploy
```

To rotate the API key:

```bash
aws ssm put-parameter \
  --name /atlas-demo/TWELVELABS_API_KEY \
  --value "tlk_NEW_KEY_HERE" \
  --type String --overwrite \
  --region us-east-1
sam deploy
```

---

## 5. Architecture Reference

### Local mode (demo)

```
Browser → Flask (app.py)
            ├── upload video → S3
            ├── generate presigned URL
            └── run workloads in background thread
                 ├── Workload 1: compliance_gate()    ─→ TwelveLabs Pegasus 1.5 (sync)
                 ├── Workload 2: quality_score()      ─→ TwelveLabs Pegasus 1.5 (sync)
                 └── Workload 3: action_annotation()  ─→ TwelveLabs Pegasus 1.5 (async)
                                                           + Marengo 3.0 search (optional)
          ↑
Browser polls /api/status every 3s — results render card by card as each workload completes
```

### AWS mode (production)

```
S3 presigned URL + video_id
  │
  ▼
Step Functions: VideoProcessingStateMachine (STANDARD)
  ├── ComplianceGate   → Lambda (120s timeout) → workloads/compliance.py
  ├── QualityScore     → Lambda (120s timeout) → workloads/quality.py
  └── ActionAnnotation → Lambda (660s timeout) → workloads/annotation.py

State passes video_url and video_id through every step unchanged.
Each Lambda writes its result to $.compliance / $.quality / $.annotation.
```

Both modes call the same `workloads/` and `utils/` code. The Lambda handlers in `lambda_handler.py` are thin wrappers — three lines each.

### Workload 3 — dual-model merge

When `MARENGO_INDEX_ID` is set (env var or Step Functions input):

1. Pegasus 1.5 async TBM → fully annotated segments
2. Marengo 3.0 semantic search → timestamp clips for the same action space
3. Merge: segments within 2 seconds of each other → both models agree, keep confidence
4. Pegasus-only or Marengo-only → `confidence: LOW`, `review_reason` set

Falls back silently to Pegasus-only if the index doesn't exist or the search fails.

### Files

```
app.py               Flask app + background threading + /api/status endpoint
lambda_handler.py    Three Lambda entry points (compliance / quality / annotation)
template.yaml        SAM template — 3 Lambda functions + Step Functions state machine
samconfig.toml       SAM deploy defaults (stack: atlas-demo, region: us-east-1)
.samignore           Excludes Flask assets and binaries from the Lambda package
workloads/
  compliance.py      Prompt + schema for Workload 1
  quality.py         Prompt + schema for Workload 2
  annotation.py      Dual-model pipeline for Workload 3
utils/
  tl_client.py       TwelveLabs client singleton (reads TWELVELABS_API_KEY)
  s3.py              Upload + presigned URL helpers (reads S3_BUCKET, AWS creds)
  evidence.py        Assembles final evidence pack from all three workload results
templates/
  index.html         Single-page UI — upload zone, real-time cards, download
```
