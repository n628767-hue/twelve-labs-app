from datetime import datetime, timezone


def assemble_evidence_pack(
    video_id: str,
    compliance: dict,
    quality: dict,
    annotation: dict,
) -> dict:
    segments = annotation.get("segments", [])

    flagged_categories = [
        cat for cat, result in compliance.get("categories", {}).items()
        if result.get("status") in ("FLAGGED", "UNCERTAIN")
    ]

    low_conf_segments = [s for s in segments if s.get("metadata", {}).get("confidence") == "LOW"]

    disposition = compliance.get("disposition", "UNKNOWN")
    verdict = quality.get("verdict", "UNKNOWN")
    segment_count = len(segments)

    summary_parts = [
        f"Compliance gate returned {disposition}.",
        f"Quality assessment: {verdict} across {len(quality.get('dimensions', {}))} dimensions.",
        f"Action annotation produced {segment_count} segment(s).",
    ]
    if flagged_categories:
        summary_parts.append(
            f"Flagged compliance categories: {', '.join(flagged_categories)}."
        )
    if low_conf_segments:
        summary_parts.append(
            f"{len(low_conf_segments)} segment(s) marked LOW confidence and require human review."
        )

    return {
        "video_id": video_id,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "compliance_gate": compliance,
        "quality_score": quality,
        "action_segments": segments,
        "reviewer_summary": " ".join(summary_parts),
    }
