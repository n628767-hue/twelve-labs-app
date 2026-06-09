import json
from twelvelabs.types.video_context import VideoContext_Url
from twelvelabs.types.sync_response_format import SyncResponseFormat
from utils.tl_client import get_client

PROMPT = """You are evaluating egocentric first-person POV video for use as AI training data for workplace task automation.

Score the footage on five quality dimensions, each on a 1–5 integer scale, and provide a one-sentence explanation per dimension.

Dimensions:
1. framing_stability — Camera steadiness and consistent framing of the work area
   (5=rock steady, 4=minor drift, 3=moderate shake, 2=frequent instability, 1=unusable shake)
2. action_visibility — How clearly the worker's hands and tools are visible during tasks
   (5=hands always clear, 4=mostly clear, 3=partially obscured, 2=frequently blocked, 1=hands rarely visible)
3. task_completeness — Whether the footage captures complete task sequences start-to-finish
   (5=full sequence, 4=minor gaps, 3=some steps missing, 2=significant gaps, 1=fragment only)
4. audio_intelligibility — Clarity of any spoken instructions or ambient task sounds
   (5=crystal clear, 4=mostly clear, 3=some noise, 2=difficult to understand, 1=inaudible/absent)
5. lighting_adequacy — Whether lighting allows clear visibility of work surfaces and actions
   (5=excellent, 4=good, 3=acceptable, 2=dim/glare issues, 1=too dark/bright to use)

Overall verdict:
- PASS if all five dimensions score 4 or above
- REVIEW if any dimension scores 3 (but none below 3)
- REJECT if two or more dimensions score below 3

Return a JSON object matching the schema exactly.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "dimensions": {
            "type": "object",
            "properties": {
                "framing_stability": {"$ref": "#/$defs/Dimension"},
                "action_visibility": {"$ref": "#/$defs/Dimension"},
                "task_completeness": {"$ref": "#/$defs/Dimension"},
                "audio_intelligibility": {"$ref": "#/$defs/Dimension"},
                "lighting_adequacy": {"$ref": "#/$defs/Dimension"},
            },
            "required": [
                "framing_stability", "action_visibility", "task_completeness",
                "audio_intelligibility", "lighting_adequacy",
            ],
        },
        "verdict": {"type": "string", "enum": ["PASS", "REVIEW", "REJECT"]},
        "overall_score": {"type": "number"},
    },
    "required": ["dimensions", "verdict", "overall_score"],
    "$defs": {
        "Dimension": {
            "type": "object",
            "properties": {
                "score": {"type": "integer", "minimum": 1, "maximum": 5},
                "explanation": {"type": "string"},
            },
            "required": ["score", "explanation"],
        }
    },
}


def run_quality_score(video_url: str) -> dict:
    client = get_client()
    response = client.analyze(
        model_name="pegasus1.5",
        video=VideoContext_Url(url=video_url),
        prompt=PROMPT,
        response_format=SyncResponseFormat(type="json_schema", json_schema=SCHEMA),
    )
    return json.loads(response.data)
