"""
@category: tool
@impact: low
@description: CLI runner para processamento DSL
"""

import argparse
import dataclasses
import json
import os
import sys
from decimal import Decimal
from typing import Any, Dict, List

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.microstructure.dsl_v01 import DSLParserV01, PatternEngineV01
from src.microstructure.context_core import classify_context_core
from src.microstructure.models import BaseEvent, parse_decimal
from src.microstructure.replay import ReplayEngineV01


def _read_json_events(path: str) -> List[BaseEvent]:
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    if not raw:
        return []
    if raw.startswith("["):
        arr = json.loads(raw)
        if not isinstance(arr, list):
            raise ValueError("events JSON must be an array or JSONL")
        return [BaseEvent.from_json(x) for x in arr]
    out: List[BaseEvent] = []
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        out.append(BaseEvent.from_json(json.loads(ln)))
    return out


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _read_params(path: str) -> Dict[str, Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError("params JSON must be an object: {pattern_name: {param: value}}")
    return obj  # type: ignore[return-value]


def _parse_tick_sizes(spec: str) -> Dict[str, Decimal]:
    out: Dict[str, Decimal] = {}
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    for p in parts:
        if "=" not in p:
            raise ValueError("tick-sizes must be instrument=tick_size,...")
        inst, v = p.split("=", 1)
        out[inst.strip()] = parse_decimal(v.strip(), "tick_size")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True, help="Path to base events JSON (array or JSONL)")
    ap.add_argument("--dsl", required=True, help="Path to DSL v0.1 text")
    ap.add_argument("--params", required=True, help="Path to JSON parameter bindings")
    ap.add_argument("--tick-sizes", required=True, help="instrument_id=tick_size,...")
    ap.add_argument("--enabled-patterns", default="", help="Comma-separated pattern names (default: all)")
    ap.add_argument("--profile", default="trader", help="iniciante|beginner|trader")
    args = ap.parse_args()

    base_events = _read_json_events(args.events)
    dsl_text = _read_text(args.dsl)
    params = _read_params(args.params)
    tick_sizes = _parse_tick_sizes(args.tick_sizes)

    patterns = DSLParserV01().parse(dsl_text)
    replay_result = ReplayEngineV01(tick_size_by_instrument=tick_sizes).replay(base_events)
    records = replay_result.records
    derived_events = replay_result.derived_events

    enabled = [p.strip() for p in args.enabled_patterns.split(",") if p.strip()] or None
    occ = PatternEngineV01(patterns).run(records, pattern_params=params, enabled_patterns=enabled)
    context = classify_context_core(records, occ, lookback_ms=1000, profile=args.profile)

    profile_norm = str(args.profile).strip().lower()
    if profile_norm in ("iniciante", "beginner"):
        include_occurrences = False
    elif profile_norm == "trader":
        include_occurrences = True
    else:
        include_occurrences = True

    out = {
        "derived_events": [
            {**dataclasses.asdict(d.envelope), "parent_event_id": d.parent_event_id, **d.payload} for d in derived_events
        ],
        "pattern_occurrences": (
            [
                {
                    "pattern": o.pattern,
                    "stream_key": list(o.stream_key),
                    "start_ts": o.start_ts,
                    "end_ts": o.end_ts,
                    "emit": o.emit,
                    "evidence_event_ids": o.evidence_event_ids,
                }
                for o in occ
            ]
            if include_occurrences
            else []
        ),
        "context": context,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
