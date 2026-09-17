from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

BASE = os.getenv("MRC_PAPER_INTERNAL_BASE", "http://mrc-cockpit-public.railway.internal:8081").rstrip("/")
EXPECTED_RELEASE = os.getenv("MRC_EXPECTED_PAPER_RELEASE", "de7a2d08a25bd78de66c2c1bd3f72056451ba435").strip()
POLL_SECONDS = max(30, int(os.getenv("MRC_EVIDENCE_POLL_SECONDS", "60")))
HISTORY_LIMIT = max(12, min(720, int(os.getenv("MRC_EVIDENCE_HISTORY_LIMIT", "120"))))
LOG_HEARTBEAT_POLLS = max(1, int(os.getenv("MRC_EVIDENCE_LOG_HEARTBEAT_POLLS", "60")))
MAX_STALE_SECONDS = max(180, POLL_SECONDS * 3)

LOCK = threading.Lock()
RESULT: dict = {"status": "STARTING", "phase": "PROSPECTIVE_EVIDENCE_COLLECTION"}
HISTORY: deque[dict] = deque(maxlen=HISTORY_LIMIT)
SNAPSHOT_SEQ = 0
LAST_LOGGED_FINGERPRINT: str | None = None
LAST_LOGGED_STATUS: str | None = None
LAST_LOGGED_SEQ = 0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch(path: str) -> dict:
    with urlopen(BASE + path, timeout=10) as r:
        return json.loads(r.read().decode())


def sample_band(closed: int) -> str:
    if closed <= 0:
        return "N0"
    if closed < 10:
        return "N1_9"
    if closed < 30:
        return "N10_29"
    if closed < 50:
        return "N30_49"
    return "N50_PLUS"


def evaluate(ready: dict, audit: dict, costs: dict, evidence: dict, previous: dict | None = None) -> dict:
    p = audit.get("prospective") or {}
    cp = audit.get("cost_policy") or {}
    cs = audit.get("cost_sensitivity") or {}
    storage = audit.get("storage") or {}
    rc = audit.get("risk_controls") or {}
    eq = evidence.get("evidence_quality") or {}

    closed = int(p.get("closed_trades") or 0)
    decisions = int(p.get("decision_events") or 0)
    candidates = int(p.get("breakout_candidates") or 0)
    paper_trades = int(p.get("paper_trades_total") or 0)
    open_position = bool(p.get("open_position"))
    current_release = audit.get("release_sha")

    monotonic = {
        "decision_events_monotonic": True,
        "breakout_candidates_monotonic": True,
        "paper_trades_monotonic": True,
        "closed_trades_monotonic": True,
    }
    regression_details: list[str] = []
    if previous and previous.get("paper_release") == current_release:
        pe = previous.get("economic_evidence") or {}
        pairs = (
            ("decision_events", decisions, "decision_events_monotonic"),
            ("breakout_candidates", candidates, "breakout_candidates_monotonic"),
            ("paper_trades_total", paper_trades, "paper_trades_monotonic"),
            ("closed_trades", closed, "closed_trades_monotonic"),
        )
        for field, current, check_name in pairs:
            prior = int(pe.get(field) or 0)
            ok = current >= prior
            monotonic[check_name] = ok
            if not ok:
                regression_details.append(f"{field}:{prior}->{current}")

    release_chain_ok = (
        ready.get("release_sha") == EXPECTED_RELEASE
        and current_release == EXPECTED_RELEASE
        and costs.get("release_sha") == EXPECTED_RELEASE
        and evidence.get("release_sha") == EXPECTED_RELEASE
    )

    operational_checks = {
        "paper_ready": ready.get("ready") is True,
        "btc_ready": (ready.get("checks") or {}).get("BTCUSDT") is True,
        "eth_ready": (ready.get("checks") or {}).get("ETHUSDT") is True,
        "coverage_gap_clear": ready.get("coverage_gap") is None,
        "durable_storage": storage.get("durable") is True and ready.get("durable_storage") is True,
        "release_pinned_across_endpoints": release_chain_ok,
        "paper_mode": audit.get("mode") == "PAPER_STAGING" == evidence.get("mode"),
        "cost_scenarios_present": all(k in cs for k in ("baseline_6bps", "stress_10bps", "stress_15bps")),
        "baseline_6bps_preserved": abs(float(cp.get("paper_baseline_bps") or 0) - 6.0) < 1e-9,
        "demo_calibration_recorded": float(cp.get("demo_calibration_bps") or 0) > 0,
        "one_global_position_enforced": rc.get("one_global_position") == "database_enforced",
        "evidence_endpoint_read_only": eq.get("read_only") is True,
        "evidence_integrity_pass": eq.get("integrity_pass") is True and ready.get("evidence_integrity_pass") is True,
        "evidence_decision_count_matches_audit": int(eq.get("decision_events_total") or 0) == decisions,
        "evidence_signal_count_matches_audit": int(eq.get("signals_total") or 0) == candidates,
        "evidence_trade_count_matches_audit": int(eq.get("paper_trades_total") or 0) == paper_trades,
        "evidence_closed_count_matches_audit": int(eq.get("closed_paper_trades") or 0) == closed,
        "evidence_open_count_matches_audit": int(eq.get("open_paper_trades") or 0) == (1 if open_position else 0),
        **monotonic,
    }

    if closed == 0:
        sample_state = "NO_CLOSED_PROSPECTIVE_TRADES"
    else:
        sample_state = "PROSPECTIVE_TRADES_ACCUMULATING"

    economic = {
        "sample_state": sample_state,
        "sample_band": sample_band(closed),
        "sample_band_role": "descriptive_only_not_an_automatic_promotion_threshold",
        "decision_events": decisions,
        "breakout_candidates": candidates,
        "paper_trades_total": paper_trades,
        "closed_trades": closed,
        "open_position": open_position,
        "wins": p.get("wins"),
        "losses": p.get("losses"),
        "win_rate": p.get("win_rate"),
        "expectancy_net_R": p.get("expectancy_net_R"),
        "total_net_R": p.get("total_net_R"),
        "profit_factor_net": p.get("profit_factor_net"),
        "max_drawdown_R": p.get("max_drawdown_R"),
        "avg_cost_R": p.get("avg_cost_R"),
        "avg_gross_R": p.get("avg_gross_R"),
        "realized_pnl": p.get("realized_pnl"),
        "equity": p.get("equity"),
        "daily_realized_pnl_utc": p.get("daily_realized_pnl_utc"),
        "cost_sensitivity": cs,
        "demo_calibration_bps": cp.get("demo_calibration_bps"),
        "evidence_quality": eq,
    }

    r0_block_reasons = [
        "HUMAN_APPROVAL_REQUIRED",
        "PRODUCTION_CREDENTIALS_AND_ACCOUNT_NOT_IN_SCOPE",
        "PRODUCTION_SPECIFIC_RISK_AND_INCIDENT_CONTROLS_NOT_VALIDATED",
        "PRODUCTION_EXECUTION_SLIPPAGE_NOT_VALIDATED",
    ]
    if closed == 0:
        r0_block_reasons.insert(0, "NO_CLOSED_PROSPECTIVE_PAPER_TRADES")
    if regression_details:
        r0_block_reasons.insert(0, "PROSPECTIVE_COUNTER_REGRESSION_DETECTED")
    if not eq.get("integrity_pass"):
        r0_block_reasons.insert(0, "PAPER_EVIDENCE_INTEGRITY_NOT_CLEAN")
    if not all(operational_checks.values()):
        r0_block_reasons.insert(0, "PAPER_OPERATIONAL_GATE_NOT_CLEAN")

    fingerprint_payload = {
        "paper_release": current_release,
        "operational_checks": operational_checks,
        "economic_evidence": economic,
        "regression_details": regression_details,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()
    ).hexdigest()

    return {
        "status": "PASS" if all(operational_checks.values()) else "FAIL",
        "phase": "PROSPECTIVE_EVIDENCE_COLLECTION",
        "strategy": audit.get("strategy"),
        "paper_release": current_release,
        "collected_at": utc_now(),
        "poll_seconds": POLL_SECONDS,
        "snapshot_fingerprint_sha256": fingerprint,
        "operational_checks": operational_checks,
        "regression_details": regression_details,
        "economic_evidence": economic,
        "r0": {
            "real_money_allowed": False,
            "automatic_promotion_supported": False,
            "status": "BLOCKED",
            "block_reasons": r0_block_reasons,
        },
        "mutation_performed": False,
        "paper_database_mutated": False,
        "exchange_private_api_used": False,
        "history_persistence": "memory_only_recomputed_from_durable_paper_source",
    }


def collect(previous: dict | None = None) -> dict:
    ready = fetch("/readyz")
    audit = fetch("/api/audit")
    costs = fetch("/api/cost-sensitivity")
    evidence = fetch("/api/evidence")
    return evaluate(ready, audit, costs, evidence, previous)


def compact_history_item(result: dict) -> dict:
    e = result.get("economic_evidence") or {}
    return {
        "snapshot_seq": result.get("snapshot_seq"),
        "collected_at": result.get("collected_at"),
        "status": result.get("status"),
        "paper_release": result.get("paper_release"),
        "snapshot_fingerprint_sha256": result.get("snapshot_fingerprint_sha256"),
        "decision_events": e.get("decision_events"),
        "breakout_candidates": e.get("breakout_candidates"),
        "paper_trades_total": e.get("paper_trades_total"),
        "closed_trades": e.get("closed_trades"),
        "open_position": e.get("open_position"),
        "sample_band": e.get("sample_band"),
        "regression_details": result.get("regression_details") or [],
    }


def log_mode(result: dict, last_fingerprint: str | None, last_status: str | None, seq_since_log: int) -> str:
    if result.get("error") or result.get("regression_details"):
        return "FULL"
    if last_fingerprint is None or result.get("snapshot_fingerprint_sha256") != last_fingerprint:
        return "FULL"
    if last_status is None or result.get("status") != last_status:
        return "FULL"
    if seq_since_log >= LOG_HEARTBEAT_POLLS:
        return "HEARTBEAT"
    return "NONE"


def emit_log(result: dict) -> None:
    global LAST_LOGGED_FINGERPRINT, LAST_LOGGED_STATUS, LAST_LOGGED_SEQ
    mode = log_mode(result, LAST_LOGGED_FINGERPRINT, LAST_LOGGED_STATUS, int(result.get("snapshot_seq") or 0) - LAST_LOGGED_SEQ)
    if mode == "NONE":
        return
    if mode == "FULL":
        print("FORWARD_PAPER_EVIDENCE_GATE=" + json.dumps(result, separators=(",", ":"), ensure_ascii=False), flush=True)
    else:
        e = result.get("economic_evidence") or {}
        compact = {
            "snapshot_seq": result.get("snapshot_seq"),
            "status": result.get("status"),
            "paper_release": result.get("paper_release"),
            "fingerprint": result.get("snapshot_fingerprint_sha256"),
            "decision_events": e.get("decision_events"),
            "breakout_candidates": e.get("breakout_candidates"),
            "paper_trades_total": e.get("paper_trades_total"),
            "closed_trades": e.get("closed_trades"),
            "sample_band": e.get("sample_band"),
            "r0": (result.get("r0") or {}).get("status"),
        }
        print("FORWARD_PAPER_EVIDENCE_HEARTBEAT=" + json.dumps(compact, separators=(",", ":"), ensure_ascii=False), flush=True)
    LAST_LOGGED_FINGERPRINT = result.get("snapshot_fingerprint_sha256")
    LAST_LOGGED_STATUS = result.get("status")
    LAST_LOGGED_SEQ = int(result.get("snapshot_seq") or 0)


def refresh_once() -> dict:
    global RESULT, SNAPSHOT_SEQ
    with LOCK:
        previous = RESULT if RESULT.get("status") in ("PASS", "FAIL") and RESULT.get("paper_release") else None
    try:
        out = collect(previous)
    except Exception as exc:
        out = {
            "status": "FAIL",
            "phase": "PROSPECTIVE_EVIDENCE_COLLECTION",
            "collected_at": utc_now(),
            "error": f"{type(exc).__name__}: {exc}",
            "r0": {
                "status": "BLOCKED",
                "real_money_allowed": False,
                "automatic_promotion_supported": False,
                "block_reasons": ["PAPER_EVIDENCE_REFRESH_FAILED", "HUMAN_APPROVAL_REQUIRED"],
            },
            "mutation_performed": False,
            "paper_database_mutated": False,
            "exchange_private_api_used": False,
        }
    with LOCK:
        SNAPSHOT_SEQ += 1
        out["snapshot_seq"] = SNAPSHOT_SEQ
        RESULT = out
        HISTORY.append(compact_history_item(out))
    emit_log(out)
    return out


def poll_loop(stop: threading.Event) -> None:
    while not stop.wait(POLL_SECONDS):
        refresh_once()


def snapshot() -> dict:
    with LOCK:
        return json.loads(json.dumps(RESULT))


def history() -> list[dict]:
    with LOCK:
        return list(HISTORY)


class H(BaseHTTPRequestHandler):
    def _json(self, body_obj: object, status: int = 200):
        body = json.dumps(body_obj, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        current = snapshot()
        if self.path == "/healthz":
            collected_at = current.get("collected_at")
            age = None
            if collected_at:
                try:
                    age = time.time() - datetime.fromisoformat(collected_at).timestamp()
                except Exception:
                    age = None
            fresh = age is not None and age <= MAX_STALE_SECONDS
            ok = current.get("status") == "PASS" and fresh
            self._json({
                "ok": ok,
                "status": current.get("status"),
                "phase": current.get("phase"),
                "snapshot_seq": current.get("snapshot_seq"),
                "snapshot_fingerprint_sha256": current.get("snapshot_fingerprint_sha256"),
                "collected_at": collected_at,
                "snapshot_age_s": round(age, 1) if age is not None else None,
                "fresh": fresh,
                "paper_release": current.get("paper_release"),
                "r0": current.get("r0"),
            }, 200 if ok else 503)
        elif self.path in ("/", "/snapshot"):
            self._json(current, 200 if current.get("status") == "PASS" else 503)
        elif self.path == "/history":
            self._json({"persistence": "memory_only", "items": history()})
        else:
            self._json({"error": "not_found"}, 404)

    def log_message(self, *args):
        return


def main():
    refresh_once()
    stop = threading.Event()
    worker = threading.Thread(target=poll_loop, args=(stop,), daemon=True, name="paper-evidence-poller")
    worker.start()
    try:
        ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), H).serve_forever()
    finally:
        stop.set()


if __name__ == "__main__":
    main()
