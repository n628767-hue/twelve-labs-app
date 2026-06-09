# Atlas Demo Guide — SE Playbook

For general project documentation see [README.md](README.md).

---

## 1. Quick Start — Running in 30 Minutes

### What you need

- Python 3.9+
- TwelveLabs API key (get one at platform.twelvelabs.io)
- AWS credentials + an S3 bucket
- A short egocentric / POV workplace video (MP4, MOV, or AVI)

### Steps

```bash
git clone https://github.com/n628767-hue/twelve-labs-app.git
cd twelve-labs-app
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:

```
TWELVELABS_API_KEY=tlk_...
S3_BUCKET=your-bucket-name
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

```bash
# macOS: port 5000 is taken by AirPlay Receiver
flask run --port 5001
```

Open `http://localhost:5001`. If you see the upload zone, you're ready.

### Smoke test

Drop in any short video and click **Run Full Intelligence Pipeline**. You should see "Compliance Gate running… Step 1 of 3" within a few seconds. If you get an error, check that your S3 bucket exists and the API key is valid.

---

## 2. Adapting for a New Customer

The workloads are prompt-driven. Changing the use case means editing prompts — no infrastructure changes.

### Workload 1 — What gets screened

**File:** `workloads/compliance.py` → edit `PROMPT` and `SCHEMA`

The six categories, severity levels, and PASS / REVIEW REQUIRED / BLOCK logic are all in the prompt. Examples:
- Healthcare: add `patient_data_visible`, remove `competitor_ip`
- Construction: replace `health_related_activity` with `fall_hazard_proximity`
- Retail: add `cash_handling_visible`, `customer_face_captured`

### Workload 2 — What quality means

**File:** `workloads/quality.py` → edit `PROMPT` and `SCHEMA`

The five 1–5 dimensions are defined in the prompt. Reweight or replace them:
- Surgical robotics training data: `action_visibility` and `lighting_adequacy` are critical; `audio_intelligibility` less so
- Customer service training data: swap physical dimensions for `speaker_clarity` and `interaction_completeness`

### Workload 3 — What actions get annotated

**File:** `workloads/annotation.py` → edit `SEGMENT_DESCRIPTION` and `FIELDS`

The `FIELDS` list controls what metadata Pegasus extracts per segment. Remove `hand` for non-physical tasks. Add a `tool_used` field for equipment-heavy workflows. The `task_type` enum (`preparation`, `active task`, `transition`, `completion`) can be replaced with domain-specific phases.

### Other changes per customer

| What | Where |
|---|---|
| App name / branding | `templates/index.html` — `<title>` and `<header>` |
| S3 bucket | `.env` → `S3_BUCKET` |
| AWS region | `.env` → `AWS_REGION` |
| Evidence pack structure | `utils/evidence.py` → `assemble_evidence_pack()` |

---

## 3. Running the Demo

### Before you start

Have a 2–5 minute egocentric / POV workplace video ready. Real customer footage lands better, but any first-person task video works. Make sure `flask run --port 5001` is running.

### Walkthrough

**Upload**
Drop the video on the upload zone and click **Run Full Intelligence Pipeline**. The video uploads to S3 and processing starts immediately.

**Step 1 — Compliance Gate (~30–60 seconds)**
Point to the step counter: *"You can see it's on Step 1 of 3 — Compliance Gate is running right now."* The dot on Card 1 pulses while active and turns green when done. Walk through the six categories and the PASS / REVIEW REQUIRED / BLOCK disposition. If anything is flagged, show the evidence text and timestamp.

> Talking point: *"This is structured output a reviewer can act on — not a summary paragraph. Every flag has a severity, a timestamp, and a recommended action."*

**Step 2 — Quality Score (~30–60 seconds)**
Show the five dimension scores and the overall verdict. Note the score bars.

> Talking point: *"This is what an AI training data pipeline needs before ingestion — objective quality gates, not manual spot-checking. A score below 3 on any dimension triggers REVIEW automatically."*

**Step 3 — Action Annotation (2–8 minutes)**
This takes longer because of the async TBM extraction. Use the wait to explain what's happening. When it populates, show the time-coded segments with verb/noun/hand labels. If Marengo dual-model is enabled, point out any LOW confidence segments with `review_reason`.

> Talking point: *"This is structured ground truth for training action recognition models — produced automatically. The dual-model merge means anything only one model detected gets flagged for human review rather than silently included."*

**Evidence pack**
Click **Download JSON**. Open it and show the structure: all three outputs in a single artifact with a reviewer summary at the top.

> Talking point: *"One upload, three AI workloads, one audit-ready document. In the Lambda deployment this is the output of a Step Functions execution — fully automated, no human in the loop unless the evidence pack says otherwise."*

---

## 4. Handing Off to Another SE

### What to share

1. Access to this repo
2. A fresh TwelveLabs API key (create a new one — don't share yours)
3. AWS credentials with S3 read/write on the demo bucket
4. The name of the S3 bucket and the AWS region

### Set up the TwelveLabs MCP plugin in Claude Code

This lets the next SE interact with TwelveLabs directly from Claude Code — list indexes, search videos, run analyses — without leaving the conversation.

```bash
# Run inside the project directory
claude plugin install twelvelabs@twelvelabs-plugins
```

Create `.claude/settings.json` in the project root:

```json
{
  "enabledPlugins": {
    "twelvelabs@twelvelabs-plugins": true
  }
}
```

The plugin reads `TWELVELABS_API_KEY` from the environment automatically. With it active, the SE can ask things like "list my indexes", "search for the moment the worker picks up the wrench", or "what videos do I have?" and get live results inline.

### If handing off a deployed AWS instance

The stack is named `atlas-demo` in `us-east-1`. The API key lives in SSM at `/atlas-demo/TWELVELABS_API_KEY`. To rotate it for the new SE:

```bash
aws ssm put-parameter \
  --name /atlas-demo/TWELVELABS_API_KEY \
  --value "tlk_NEW_KEY_HERE" \
  --type String --overwrite \
  --region us-east-1

sam build && sam deploy
```
