"""Lambda entry points for the Atlas video processing pipeline.

Each handler receives the Step Functions state as `event`, which always contains
at minimum {"video_url": "...", "video_id": "..."}. ResultPath in the state
machine definition merges each handler's return value into the state under
$.compliance, $.quality, and $.annotation respectively — video_url and video_id
pass through untouched to every downstream state.
"""
from workloads.compliance import run_compliance_gate
from workloads.quality import run_quality_score
from workloads.annotation import run_action_annotation


def compliance_handler(event, context):
    return run_compliance_gate(event["video_url"])


def quality_handler(event, context):
    return run_quality_score(event["video_url"])


def annotation_handler(event, context):
    return run_action_annotation(
        event["video_url"],
        marengo_index_id=event.get("marengo_index_id"),
    )
