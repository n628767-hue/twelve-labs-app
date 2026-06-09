import json
import os
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
MERGE_WINDOW_S = 2.0

# Broad action-space queries that map to the same segment space as the Pegasus TBM task
MARENGO_QUERIES = [
    "worker performing a purposeful hand movement or tool interaction",
    "preparation active task transition completion workplace action",
]


def run_action_annotation(
    video_url: str,
    marengo_index_id: str = None,
    marengo_video_id: str = None,
) -> dict:
    client = get_client()

    marengo_index_id = marengo_index_id or os.environ.get("MARENGO_INDEX_ID")
    marengo_video_id = marengo_video_id or os.environ.get("MARENGO_VIDEO_ID")

    pegasus_result = _run_pegasus(client, video_url)

    # Fall back to Pegasus-only if no Marengo index configured or Pegasus itself failed
    if not marengo_index_id or pegasus_result["status"] != "ready":
        return pegasus_result

    try:
        marengo_clips = _run_marengo_search(client, marengo_index_id, marengo_video_id)
    except Exception:
        # Marengo index doesn't exist yet or search failed — degrade gracefully
        return pegasus_result

    merged = _merge_segments(pegasus_result["segments"], marengo_clips)
    return {
        "task_id": pegasus_result["task_id"],
        "status": "ready",
        "segments": merged,
        "low_confidence_count": sum(1 for s in merged if s.get("confidence") == "LOW"),
        "models": ["pegasus1.5", "marengo3.0"],
    }


def _run_pegasus(client, video_url: str) -> dict:
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


def _run_marengo_search(client, index_id: str, video_id: str = None) -> list:
    """Run Marengo semantic search; return deduplicated clips sorted by start time."""
    raw_clips = []
    for query in MARENGO_QUERIES:
        kwargs = dict(index_id=index_id, query_text=query, options=["visual", "audio"])
        if video_id:
            kwargs["filter"] = {"id": [video_id]}
        results = client.search.query(**kwargs)
        for clip in (results.data or []):
            raw_clips.append({
                "start": float(clip.start),
                "end": float(clip.end),
                "score": float(clip.score),
            })

    raw_clips.sort(key=lambda c: c["start"])

    deduped = []
    for clip in raw_clips:
        if not deduped or clip["start"] - deduped[-1]["start"] > MERGE_WINDOW_S:
            deduped.append(clip)
    return deduped


def _seg_start(seg: dict) -> float:
    """Extract start time from a segment, handling both 'start' and 'start_time' keys."""
    return float(seg.get("start") or seg.get("start_time") or 0)


def _merge_segments(pegasus_segs: list, marengo_clips: list) -> list:
    """
    Merge Pegasus annotations with Marengo clips.

    Matching rule: Pegasus segment and Marengo clip are the same action if their
    start times are within MERGE_WINDOW_S of each other.

    - Both models agree  → keep Pegasus annotation and confidence unchanged.
    - Pegasus only       → confidence forced to LOW, review_reason: pegasus_only.
    - Marengo only       → synthetic LOW-confidence segment, review_reason: marengo_only.
    """
    matched_marengo: set[int] = set()
    merged = []

    for seg in pegasus_segs:
        start = _seg_start(seg)
        match_idx = next(
            (
                i for i, c in enumerate(marengo_clips)
                if i not in matched_marengo and abs(start - c["start"]) <= MERGE_WINDOW_S
            ),
            None,
        )
        if match_idx is not None:
            matched_marengo.add(match_idx)
            merged.append(seg)
        else:
            merged.append({**seg, "confidence": "LOW", "review_reason": "pegasus_only"})

    for i, clip in enumerate(marengo_clips):
        if i not in matched_marengo:
            merged.append({
                "start": clip["start"],
                "end": clip["end"],
                "title": "Unmatched action",
                "task_type": "active task",
                "verb": None,
                "noun": None,
                "hand": None,
                "confidence": "LOW",
                "description": "Action detected by Marengo only — requires human review.",
                "review_reason": "marengo_only",
            })

    merged.sort(key=_seg_start)
    return merged


def _normalize(raw) -> list:
    """Flatten whatever shape the TBM response comes back in."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("action_segment", "segments", "data", "results"):
            if key in raw and isinstance(raw[key], list):
                return raw[key]
    return []
