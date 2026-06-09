# FieldLens Atlas — Workforce Video Intelligence

Egocentric first-person POV video from frontline workers, processed through three AI workloads: compliance screening, training-data quality scoring, and action annotation. Runs as a local Flask app for development and as an AWS Lambda + Step Functions pipeline for production.

---

## Architecture

```
Local (Flask)                     AWS (Lambda + Step Functions)
─────────────────────             ──────────────────────────────────────────
Browser → app.py                  S3 presigned URL
  ├─ upload to S3                   │
  ├─ generate presigned URL         ▼
  └─ run workloads in-process   VideoProcessingStateMachine (STANDARD)
       ├─ compliance_gate           ├─ ComplianceGate  → ComplianceFunction
       ├─ quality_score             ├─ QualityScore    → QualityFunction
       └─ action_annotation         └─ ActionAnnotation → AnnotationFunction
```

Both paths call the same code in `workloads/` and `utils/`. `app.py` runs all three workloads synchronously; the Step Functions pipeline runs them as chained Lambda invocations.

---

## Workloads

### Workload 1 — Compliance Gate (`workloads/compliance.py`)
Pegasus 1.5 synchronous analysis. Screens six categories (minors in frame, PII, profanity, unsafe acts, competitor IP, health-related activity) and returns a disposition of `PASS`, `REVIEW REQUIRED`, or `BLOCK`.

### Workload 2 — Quality Score (`workloads/quality.py`)
Pegasus 1.5 synchronous analysis. Scores five training-data quality dimensions (framing stability, action visibility, task completeness, audio intelligibility, lighting adequacy) on a 1–5 scale and returns a verdict of `PASS`, `REVIEW`, or `REJECT`.

### Workload 3 — Action Annotation (`workloads/annotation.py`)
Dual-model pipeline when a Marengo index is configured; falls back to Pegasus-only otherwise.

**Dual-model flow:**
1. **Pegasus 1.5** — async time-based metadata extraction producing fully annotated action segments (title, verb, noun, hand, task_type, confidence).
2. **Marengo 3.0** — semantic search over the same indexed video for the same action space.
3. **Merge** — segments from both models within 2 seconds of each other are considered the same action. Segments detected by only one model are flagged `confidence: LOW` and routed to human review via `review_reason: pegasus_only` or `review_reason: marengo_only`.

**Activating the dual-model path** requires passing `marengo_index_id` (and optionally `marengo_video_id`) in the Step Functions input, or setting `MARENGO_INDEX_ID` / `MARENGO_VIDEO_ID` as Lambda environment variables in `template.yaml`.

---

## Local Development

### Prerequisites
- Python 3.9+
- AWS credentials configured (`~/.aws/credentials` or environment variables)
- TwelveLabs API key

### Setup
```bash
git clone https://github.com/n628767-hue/twelve-labs-app.git
cd twelve-labs-app
pip install -r requirements.txt
cp .env.example .env
# edit .env and fill in TWELVELABS_API_KEY and S3_BUCKET
```

### Run
```bash
# macOS: port 5000 is reserved by AirPlay Receiver — use 5001
flask run --port 5001
```

The app is available at `http://localhost:5001`. Upload a video via the browser UI; the three workloads run in sequence and return an evidence pack as JSON.

### Environment variables (`.env`)
| Variable | Description |
|---|---|
| `TWELVELABS_API_KEY` | TwelveLabs API key |
| `S3_BUCKET` | S3 bucket for video storage (default: `fieldlens-atlas-demo`) |
| `AWS_REGION` | AWS region (default: `us-east-1`) |
| `AWS_ACCESS_KEY_ID` | AWS access key (or use IAM role / `~/.aws/credentials`) |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key |
| `MARENGO_INDEX_ID` | TwelveLabs index ID for Workload 3 dual-model path (optional) |
| `MARENGO_VIDEO_ID` | TwelveLabs video ID within that index (optional) |

---

## AWS Deployment

### Prerequisites
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- Python 3.12 (SAM builds against the Lambda runtime version)
- AWS credentials with CloudFormation, Lambda, Step Functions, IAM, and S3 permissions

On macOS with Homebrew:
```bash
brew install python@3.12
# Add Homebrew to PATH if on Apple Silicon:
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc && source ~/.zshrc
```

### 1. Store the TwelveLabs API key in SSM Parameter Store

CloudFormation resolves SSM parameters of type `String` at deploy time. Create the parameter before deploying:

```bash
aws ssm put-parameter \
  --name /atlas-demo/TWELVELABS_API_KEY \
  --value "tlk_YOUR_KEY_HERE" \
  --type String \
  --region us-east-1
```

> **Note:** Use `--type String` (not `SecureString`). CloudFormation's `AWS::SSM::Parameter::Value<String>` cannot resolve `SecureString` parameters. The Lambda environment variable is encrypted at rest by AWS regardless.

To rotate the key: update the SSM parameter and redeploy (`sam deploy`).

### 2. Build

```bash
sam build
```

SAM installs dependencies into `.aws-sam/build/` and copies source. The `.samignore` file excludes Flask templates, static assets, uploads, and the installer binary from the Lambda package.

### 3. Deploy

```bash
sam deploy
```

On first run, SAM creates a managed S3 bucket for deployment artifacts. Subsequent deploys reuse it. Stack name, region, and other defaults are in `samconfig.toml`.

The deploy creates:
- `ComplianceFunction` — 512 MB, 120s timeout
- `QualityFunction` — 512 MB, 120s timeout
- `AnnotationFunction` — 512 MB, 660s timeout (Pegasus async polling runs up to 600s)
- `VideoProcessingStateMachine` — STANDARD type Step Functions state machine
- IAM execution roles for each function and the state machine

### 4. Trigger an execution

The state machine expects `video_url` (an HTTP-accessible URL TwelveLabs can fetch) and `video_id` (your internal identifier). Generate a presigned URL from S3 first:

```bash
aws s3 presign s3://YOUR_BUCKET/videos/YOUR_VIDEO.mp4 --expires-in 7200
```

Then start the execution:

```bash
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:us-east-1:ACCOUNT:stateMachine:VideoProcessingStateMachine-XXXXX \
  --input '{
    "video_url": "https://...",
    "video_id": "your-uuid"
  }'
```

To use the Workload 3 dual-model path, add the Marengo index and video IDs:

```bash
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:us-east-1:ACCOUNT:stateMachine:VideoProcessingStateMachine-XXXXX \
  --input '{
    "video_url": "https://...",
    "video_id": "your-uuid",
    "marengo_index_id": "YOUR_INDEX_ID",
    "marengo_video_id": "YOUR_VIDEO_ID"
  }'
```

The execution output (available in the Step Functions console or via `describe-execution`) will contain `$.compliance`, `$.quality`, and `$.annotation` fields with the full results from each workload.

### State machine data flow

```
Input:  { "video_url": "...", "video_id": "..." }
          │
          ▼ ComplianceGate  (ResultPath: $.compliance)
        { "video_url": "...", "video_id": "...", "compliance": { ... } }
          │
          ▼ QualityScore    (ResultPath: $.quality)
        { ..., "compliance": { ... }, "quality": { ... } }
          │
          ▼ ActionAnnotation (ResultPath: $.annotation)
        { ..., "compliance": { ... }, "quality": { ... }, "annotation": { ... } }
```

`video_url` and `video_id` pass through to every state unchanged.

---

## MCP Server Setup (Claude Code)

This project uses the [TwelveLabs Claude Code plugin](https://github.com/twelvelabs/twelvelabs-plugins), which exposes TwelveLabs API operations as MCP tools directly in Claude Code.

The plugin is enabled via `.claude/settings.json`:

```json
{
  "enabledPlugins": {
    "twelvelabs@twelvelabs-plugins": true
  }
}
```

To install the plugin, run inside this project directory:

```bash
claude plugin install twelvelabs@twelvelabs-plugins
```

The plugin requires `TWELVELABS_API_KEY` to be set in your environment (or `.env`). Once installed, Claude Code can list indexes, list videos, search, and run analyses against TwelveLabs directly from the conversation.

---

## Project Structure

```
.
├── app.py                  # Flask app — local development entry point
├── lambda_handler.py       # Lambda entry points (three handlers)
├── template.yaml           # SAM template — Lambda functions + state machine
├── samconfig.toml          # SAM deploy defaults
├── .samignore              # Files excluded from the Lambda package
├── requirements.txt        # Python dependencies
├── workloads/
│   ├── compliance.py       # Workload 1 — compliance gate (Pegasus 1.5)
│   ├── quality.py          # Workload 2 — quality score (Pegasus 1.5)
│   └── annotation.py       # Workload 3 — action annotation (Pegasus 1.5 + Marengo 3.0)
├── utils/
│   ├── tl_client.py        # TwelveLabs client singleton
│   ├── s3.py               # S3 upload and presigned URL helpers
│   └── evidence.py         # Evidence pack assembly
└── templates/
    └── index.html          # Flask UI
```
