from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.microstructure.models import EventRecord
from src.microstructure.dsl_v01 import PatternOccurrence


@dataclass(frozen=True)
class ContextSegment:
    stream_key: Tuple[str, str, str]
    start_ts: int
    end_ts: int
    event_ids: List[str]
    gap_reset_event_id: Optional[str]


def split_segments_core(records: Sequence[EventRecord]) -> List[ContextSegment]:
    """
    Core rule: context is evaluated per stream and cannot cross SEQUENCE_GAP/BOOK_RESET.
    """
    per_stream: Dict[Tuple[str, str, str], List[EventRecord]] = {}
    for r in records:
        per_stream.setdefault(r.envelope.stream_key(), []).append(r)

    out: List[ContextSegment] = []
    for sk in sorted(per_stream.keys()):
        stream = sorted(per_stream[sk], key=lambda r: (r.effective_ts(), r.envelope.event_id))
        cur_ids: List[str] = []
        seg_start: Optional[int] = None
        last_ts: Optional[int] = None
        pending_gap_reset: Optional[str] = None

        for r in stream:
            if r.envelope.event_type in ("SEQUENCE_GAP", "BOOK_RESET"):
                if cur_ids and seg_start is not None and last_ts is not None:
                    out.append(
                        ContextSegment(
                            stream_key=sk,
                            start_ts=seg_start,
                            end_ts=last_ts,
                            event_ids=list(cur_ids),
                            gap_reset_event_id=pending_gap_reset,
                        )
                    )
                cur_ids = []
                seg_start = None
                last_ts = None
                pending_gap_reset = r.envelope.event_id
                continue

            ts = r.effective_ts()
            if seg_start is None:
                seg_start = ts
            last_ts = ts
            cur_ids.append(r.envelope.event_id)

        if cur_ids and seg_start is not None and last_ts is not None:
            out.append(
                ContextSegment(
                    stream_key=sk,
                    start_ts=seg_start,
                    end_ts=last_ts,
                    event_ids=list(cur_ids),
                    gap_reset_event_id=pending_gap_reset,
                )
            )
    return out


def classify_context_core(
    records: Sequence[EventRecord],
    occurrences: Sequence[PatternOccurrence],
    *,
    lookback_ms: int = 1000,
    profile: str = "trader",
) -> List[Dict[str, Any]]:
    """
    Produces deterministic, non-operational context descriptors.

    Output is factual: it is derived only from (events, derived events, pattern occurrences).
    Each context entry includes evidence_event_ids for auditability.
    """
    profile_norm = profile.strip().lower()
    if profile_norm in ("iniciante", "beginner"):
        profile_norm = "beginner"
    elif profile_norm in ("trader",):
        profile_norm = "trader"
    else:
        raise ValueError("profile must be one of: iniciante|beginner|trader")

    segs = split_segments_core(records)
    occ_by_stream: Dict[Tuple[str, str, str], List[PatternOccurrence]] = {}
    for o in occurrences:
        occ_by_stream.setdefault(o.stream_key, []).append(o)

    records_by_stream: Dict[Tuple[str, str, str], List[EventRecord]] = {}
    for r in records:
        records_by_stream.setdefault(r.envelope.stream_key(), []).append(r)
    for sk in list(records_by_stream.keys()):
        records_by_stream[sk].sort(key=lambda r: (r.effective_ts(), r.envelope.event_id))

    contexts: List[Dict[str, Any]] = []
    for seg in segs:
        seg_occ = occ_by_stream.get(seg.stream_key, [])
        window_start = max(seg.start_ts, seg.end_ts - lookback_ms)
        recent_occ = [o for o in seg_occ if window_start <= o.end_ts <= seg.end_ts]

        stream_records = records_by_stream.get(seg.stream_key, [])
        has_snapshot = any(
            (seg.start_ts <= r.effective_ts() <= seg.end_ts) and (r.envelope.event_type == "BOOK_SNAPSHOT")
            for r in stream_records
        )

        recent_records = [r for r in stream_records if window_start <= r.effective_ts() <= seg.end_ts]
        recent_event_count = len(recent_records)
        liquidity_present = any(r.envelope.event_type in ("LIQUIDITY_ADD", "LIQUIDITY_REMOVE") for r in recent_records)
        activity = "EXPANDED" if recent_event_count >= 20 else "COMPRESSED"

        unstable_patterns = {"SpreadExpansionSequence", "TouchRepriceWithoutPrint", "LevelFlickerSequence"}
        unstable_from_patterns = any(o.pattern in unstable_patterns for o in recent_occ)
        stability = "UNSTABLE" if (not has_snapshot) or unstable_from_patterns else "STABLE"
        liquidity = "PRESENT" if liquidity_present else "ABSENT"

        do_not_operate = False
        if stability == "UNSTABLE":
            do_not_operate = True
        if liquidity == "ABSENT" and stability != "STABLE":
            do_not_operate = True

        pattern_label_map = {
            "DepletionSequence": "depletion",
            "MultiLevelErosion": "multi_level_erosion",
            "TouchRepriceWithoutPrint": "touch_reprice_without_print",
            "PrintClusterAtTouch": "print_cluster",
            "LevelFlickerSequence": "flicker",
            "SpreadExpansionSequence": "spread_expansion",
            "ReplenishAfterDepletionSequence": "replenish_after_depletion",
        }
        pattern_labels = {pattern_label_map.get(o.pattern, o.pattern) for o in recent_occ}
        if liquidity == "ABSENT":
            pattern_labels.add("liquidity_vacuum")
        patterns_detected = sorted(pattern_labels)

        out: Dict[str, Any] = {
            "stream_key": seg.stream_key,
            "segment_start_ts": seg.start_ts,
            "segment_end_ts": seg.end_ts,
            "stability": stability,
            "liquidity": liquidity,
            "activity": activity,
            "do_not_operate": do_not_operate,
            "patterns_detected": patterns_detected,
        }

        if profile_norm == "trader":
            seen_eids: set[str] = set()
            evidence_event_ids: List[str] = []
            for r in recent_records:
                eid = r.envelope.event_id
                if eid in seen_eids:
                    continue
                seen_eids.add(eid)
                evidence_event_ids.append(eid)
            for o in sorted(recent_occ, key=lambda x: (x.end_ts, x.start_ts, x.pattern)):
                for eid in o.evidence_event_ids:
                    if eid in seen_eids:
                        continue
                    seen_eids.add(eid)
                    evidence_event_ids.append(eid)
            out["lookback_ms"] = lookback_ms
            out["recent_event_count"] = recent_event_count
            out["evidence_event_ids"] = evidence_event_ids

        contexts.append(out)
    contexts.sort(key=lambda x: (x["stream_key"], x["segment_start_ts"], x["segment_end_ts"]))
    return contexts
