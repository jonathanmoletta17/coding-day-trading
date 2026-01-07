"""
@category: production
@impact: critical
@description: Context metrics V0.1 - Carrega e interpreta estabilidade/liquidez/atividade do mercado
"""
from __future__ import annotations

import logging
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContextV01Snapshot:
    stability: str
    liquidity: str
    activity: str
    do_not_operate: bool
    window_start_ms: int
    window_end_ms: int
    source_path: str
    output_sha256: Optional[str]


def find_default_metrics_path(project_root: str, symbol: str) -> Optional[str]:
    sym = symbol.strip().lower()
    if not sym:
        return None
    fname = f"context_v01_metrics_{sym}.json"
    candidates = [
        os.path.join(project_root, "artifacts_workflow_last_hour", fname),
        os.path.join(project_root, "artifacts_workflow_first_hour", fname),
        os.path.join(project_root, fname),
    ]
    existing = [p for p in candidates if os.path.exists(p)]
    if not existing:
        return None
    existing.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return existing[0]


def load_last_context_from_metrics(metrics_path: str) -> ContextV01Snapshot:
    if not metrics_path:
        raise ValueError("metrics_path is required")
    p = os.path.abspath(metrics_path)
    logger.info("context_v01.metrics load_attempt path=%s", p)
    if not os.path.exists(p):
        logger.warning("context_v01.metrics missing path=%s", p)
        raise FileNotFoundError(p)
    try:
        st = os.stat(p)
        logger.info("context_v01.metrics stat path=%s size=%d mtime=%d", p, st.st_size, int(st.st_mtime))
    except OSError as e:
        logger.warning("context_v01.metrics stat_failed path=%s err=%s", p, e)
    with open(p, "r", encoding="utf-8") as f:
        try:
            raw = json.loads(f.read())
        except json.JSONDecodeError as e:
            logger.warning("context_v01.metrics invalid_json path=%s err=%s", p, e)
            raise ValueError("metrics.json invalid JSON") from e
    windows = raw.get("windows")
    if not isinstance(windows, list) or not windows:
        logger.warning("context_v01.metrics invalid_windows path=%s", p)
        raise ValueError("metrics.json has no windows")
    last = windows[-1]
    if not isinstance(last, dict):
        logger.warning("context_v01.metrics invalid_last_window path=%s", p)
        raise ValueError("metrics.json last window is not an object")
    ctx = last.get("context")
    if not isinstance(ctx, dict):
        logger.warning("context_v01.metrics missing_context path=%s", p)
        raise ValueError("metrics.json last window has no context")

    def _req_str(k: str) -> str:
        v = ctx.get(k)
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"metrics.json context.{k} is missing/invalid")
        return v

    def _req_int_from(k: str, src: Dict[str, Any]) -> int:
        v = src.get(k)
        if isinstance(v, bool):
            raise ValueError(f"metrics.json {k} invalid")
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            return int(v)
        if isinstance(v, str) and v.strip().lstrip("-").isdigit():
            return int(v.strip())
        raise ValueError(f"metrics.json {k} missing/invalid")

    dno = ctx.get("do_not_operate")
    if not isinstance(dno, bool):
        logger.warning("context_v01.metrics invalid_do_not_operate path=%s", p)
        raise ValueError("metrics.json context.do_not_operate missing/invalid")

    snap = ContextV01Snapshot(
        stability=_req_str("stability"),
        liquidity=_req_str("liquidity"),
        activity=_req_str("activity"),
        do_not_operate=dno,
        window_start_ms=_req_int_from("window_start_ms", last),
        window_end_ms=_req_int_from("window_end_ms", last),
        source_path=p,
        output_sha256=str(raw.get("output_sha256")) if raw.get("output_sha256") is not None else None,
    )
    logger.info(
        "context_v01.metrics load_ok path=%s window_start_ms=%d window_end_ms=%d do_not_operate=%s output_sha256=%s",
        p,
        snap.window_start_ms,
        snap.window_end_ms,
        str(snap.do_not_operate).lower(),
        snap.output_sha256,
    )
    return snap
