import json
import time
from twelvelabs.types.video_context import VideoContext_Url
from twelvelabs.types.async_response_format import AsyncResponseFormat
from twelvelabs.types.segment_definition import SegmentDefinition
from twelvelabs.types.segment_field import SegmentField
from utils.tl_client import get_client

SEGMENT_DESCRIPTION = (
    "An atomic workplace action — a single, purposeful hand movement or tool interaction "
    "performed by the worker. Segment at natural action boundaries. Exclude idle periods."
)

FIELDS = [
    SegmentField(
        name="title",
        type="string",
        description="Short imperative label for this action (e.g. 'Pick up wrench', 'Tighten bolt')",
    ),
    SegmentField(
        name="task_type",
        type="string",
        description="Phase of the action",
        enum=["preparation", "active task", "transition", "completion"],
    ),
    SegmentField(
        name="verb",
        type="string",
        description="Primary action verb in infinitive form (e.g. 'pick', 'tighten', 'inspect')",
    ),
    SegmentField(
        name="noun",
        type="string",
        description="Primary object being acted upon (e.g. 'wrench', 'bolt', 'surface')",
    ),
    SegmentField(
        name="hand",
        type="string",
        description="Which hand(s) are primarily active",
        enum=["LEFT", "RIGHT", "BOTH"],
    ),
    SegmentField(
        name="confidence",
        type="string",
        description="Annotation confidence based on video clarity",
        enum=["HIGH", "MEDIUM", "LOW"],
    ),
    SegmentField(
        name="description",
        type="string",
        description="One sentence describing the action and its workplace context",
    ),
]

POLL_INTERVAL = 5
MAX_WAIT = 600


def run_action_annotation(video_url: str) -> dict:
    client = get_client()

    task = client.analyze_async.tasks.create(
        video=VideoContext_Url(url=video_url),
        model_name="pegasus1.5",
        analysis_mode="time_based_metadata",
        response_format=AsyncResponseFormat(
            type="segment_definitions",
            segment_definitions=[
                SegmentDefinition(
                    id="action_segment",
                    description=SEGMENT_DESCRIPTION,
                    fields=FIELDS,
                )
            ],
            segment_time_format="seconds",
        ),
    )

    task_id = task.task_id
    elapsed = 0
    while elapsed < MAX_WAIT:
        status = client.analyze_async.tasks.retrieve(task_id)
        if status.status == "ready":
            raw = json.loads(status.result.data)
            segments = _normalize(raw)
            return {
                "task_id": task_id,
                "status": "ready",
                "segments": segments,
                "low_confidence_count": sum(1 for s in segments if s.get("confidence") == "LOW"),
            }
        if status.status == "failed":
            error_msg = status.error.message if status.error else "unknown error"
            return {"task_id": task_id, "status": "failed", "error": error_msg, "segments": []}
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

    return {"task_id": task_id, "status": "timeout", "segments": []}


def _normalize(raw) -> list:
    """Flatten whatever shape the TBM response comes back in."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("action_segment", "segments", "data", "results"):
            if key in raw and isinstance(raw[key], list):
                return raw[key]
    return []
