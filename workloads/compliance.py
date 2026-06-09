import json
from twelvelabs.types.video_context import VideoContext_Url
from twelvelabs.types.sync_response_format import SyncResponseFormat
from utils.tl_client import get_client

PROMPT = """You are a compliance screening officer reviewing egocentric first-person POV video from a frontline worker.

Evaluate the footage against these six categories and return a JSON object matching the schema exactly.

Categories:
1. minors_in_frame — Any person who appears to be under 18 years old (P0 auto-block)
2. pii_sensitive_surfaces — Visible PII: screens showing personal data, documents, ID badges, medical records (P1)
3. profanity_hostile_speech — Audible profanity, slurs, or hostile language (P1)
4. unsafe_acts — Safety violations: missing PPE, improper tool use, fall hazards (P1)
5. competitor_ip — Visible competitor branding, trade secrets, or proprietary materials (P1)
6. health_related_activity — Visible medical procedures, medications, or health data (P1)

For each category provide:
- status: "FLAGGED", "CLEAR", or "UNCERTAIN"
- severity: "HIGH", "MEDIUM", "LOW", or null if CLEAR
- timestamp: approximate time in video as "HH:MM:SS" or null if not applicable
- evidence: one sentence describing what was observed, or null if CLEAR
- action: recommended action ("AUTO_BLOCK", "ESCALATE_TO_REVIEWER", "LOG_AND_PASS", or "PASS")

Then provide an overall assessment:
- disposition: "PASS", "REVIEW REQUIRED", or "BLOCK"
  (BLOCK if any P0 flagged; REVIEW REQUIRED if any P1 flagged; PASS if all CLEAR)
- confidence: 0.0–1.0
- reviewer_summary: 2-3 plain-language sentences for a human reviewer
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "categories": {
            "type": "object",
            "properties": {
                "minors_in_frame": {"$ref": "#/$defs/CategoryResult"},
                "pii_sensitive_surfaces": {"$ref": "#/$defs/CategoryResult"},
                "profanity_hostile_speech": {"$ref": "#/$defs/CategoryResult"},
                "unsafe_acts": {"$ref": "#/$defs/CategoryResult"},
                "competitor_ip": {"$ref": "#/$defs/CategoryResult"},
                "health_related_activity": {"$ref": "#/$defs/CategoryResult"},
            },
            "required": [
                "minors_in_frame", "pii_sensitive_surfaces", "profanity_hostile_speech",
                "unsafe_acts", "competitor_ip", "health_related_activity",
            ],
        },
        "disposition": {"type": "string", "enum": ["PASS", "REVIEW REQUIRED", "BLOCK"]},
        "confidence": {"type": "number"},
        "reviewer_summary": {"type": "string"},
    },
    "required": ["categories", "disposition", "confidence", "reviewer_summary"],
    "$defs": {
        "CategoryResult": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["FLAGGED", "CLEAR", "UNCERTAIN"]},
                "severity": {"type": ["string", "null"], "enum": ["HIGH", "MEDIUM", "LOW", None]},
                "timestamp": {"type": ["string", "null"]},
                "evidence": {"type": ["string", "null"]},
                "action": {
                    "type": "string",
                    "enum": ["AUTO_BLOCK", "ESCALATE_TO_REVIEWER", "LOG_AND_PASS", "PASS"],
                },
            },
            "required": ["status", "severity", "timestamp", "evidence", "action"],
        }
    },
}


def run_compliance_gate(video_url: str) -> dict:
    client = get_client()
    response = client.analyze(
        model_name="pegasus1.5",
        video=VideoContext_Url(url=video_url),
        prompt=PROMPT,
        response_format=SyncResponseFormat(type="json_schema", json_schema=SCHEMA),
    )
    return json.loads(response.data)
