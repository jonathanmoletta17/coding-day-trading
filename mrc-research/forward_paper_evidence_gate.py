from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import urlopen

BASE = os.getenv("MRC_PAPER_INTERNAL_BASE", "http://mrc-cockpit-public.railway.internal:8081").rstrip("/")
EXPECTED_RELEASE = os.getenv("MRC_EXPECTED_PAPER_RELEASE", "132f3e939c8074dff084f4e56049754f9030af6f").strip()


def fetch(path: str) -> dict:
    with urlopen(BASE + path, timeout=10) as r:
        return json.loads(r.read().decode())


def run() -> dict:
    ready = fetch("/readyz")
    audit = fetch("/api/audit")
    costs = fetch("/api/cost-sensitivity")

    p = audit.get("prospective") or {}
    cp = audit.get("cost_policy") or {}
    cs = audit.get("cost_sensitivity") or {}
    storage = audit.get("storage") or {}
    rc = audit.get("risk_controls") or {}

    operational_checks = {
        "paper_ready": ready.get("ready") is True,
        "btc_ready": (ready.get("checks") or {}).get("BTCUSDT") is True,
        "eth_ready": (ready.get("checks") or {}).get("ETHUSDT") is True,
        "coverage_gap_clear": ready.get("coverage_gap") is None,
        "durable_storage": storage.get("durable") is True and ready.get("durable_storage") is True,
        "release_pinned": ready.get("release_sha") == EXPECTED_RELEASE == audit.get("release_sha") == costs.get("release_sha"),
        "paper_mode": audit.get("mode") == "PAPER_STAGING",
        "cost_scenarios_present": all(k in cs for k in ("baseline_6bps", "stress_10bps", "stress_15bps")),
        "baseline_6bps_preserved": abs(float(cp.get("paper_baseline_bps") or 0) - 6.0) < 1e-9,
        "demo_calibration_recorded": float(cp.get("demo_calibration_bps") or 0) > 0,
        "one_global_position_enforced": rc.get("one_global_position") == "database_enforced",
    }

    closed = int(p.get("closed_trades") or 0)
    decisions = int(p.get("decision_events") or 0)
    candidates = int(p.get("breakout_candidates") or 0)
    paper_trades = int(p.get("paper_trades_total") or 0)

    if closed == 0:
        sample_state = "NO_CLOSED_PROSPECTIVE_TRADES"
    else:
        sample_state = "PROSPECTIVE_TRADES_ACCUMULATING"

    economic = {
        "sample_state": sample_state,
        "decision_events": decisions,
        "breakout_candidates": candidates,
        "paper_trades_total": paper_trades,
        "closed_trades": closed,
        "open_position": bool(p.get("open_position")),
        "expectancy_net_R": p.get("expectancy_net_R"),
        "profit_factor_net": p.get("profit_factor_net"),
        "max_drawdown_R": p.get("max_drawdown_R"),
        "avg_cost_R": p.get("avg_cost_R"),
        "equity": p.get("equity"),
        "cost_sensitivity": cs,
        "demo_calibration_bps": cp.get("demo_calibration_bps"),
    }

    r0_block_reasons = [
        "HUMAN_APPROVAL_REQUIRED",
        "PRODUCTION_CREDENTIALS_AND_ACCOUNT_NOT_IN_SCOPE",
        "PRODUCTION_SPECIFIC_RISK_AND_INCIDENT_CONTROLS_NOT_VALIDATED",
        "PRODUCTION_EXECUTION_SLIPPAGE_NOT_VALIDATED",
    ]
    if closed == 0:
        r0_block_reasons.insert(0, "NO_CLOSED_PROSPECTIVE_PAPER_TRADES")
    if not all(operational_checks.values()):
        r0_block_reasons.insert(0, "PAPER_OPERATIONAL_GATE_NOT_CLEAN")

    out = {
        "status": "PASS" if all(operational_checks.values()) else "FAIL",
        "phase": "PROSPECTIVE_EVIDENCE_COLLECTION",
        "strategy": audit.get("strategy"),
        "paper_release": audit.get("release_sha"),
        "operational_checks": operational_checks,
        "economic_evidence": economic,
        "r0": {
            "real_money_allowed": False,
            "automatic_promotion_supported": False,
            "status": "BLOCKED",
            "block_reasons": r0_block_reasons,
        },
        "mutation_performed": False,
        "exchange_private_api_used": False,
    }
    print("FORWARD_PAPER_EVIDENCE_GATE=" + json.dumps(out, separators=(",", ":"), ensure_ascii=False), flush=True)
    return out


class H(BaseHTTPRequestHandler):
    RESULT = {"status": "STARTING"}
    def do_GET(self):
        if self.path in ("/", "/healthz"):
            body = json.dumps(self.RESULT, separators=(",", ":")).encode()
            self.send_response(200 if self.RESULT.get("status") == "PASS" else 503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()
    def log_message(self, *args): return


def main():
    try:
        H.RESULT = run()
    except Exception as e:
        H.RESULT = {"status":"FAIL","phase":"PROSPECTIVE_EVIDENCE_COLLECTION","error":f"{type(e).__name__}: {e}","r0":{"status":"BLOCKED","real_money_allowed":False}}
        print("FORWARD_PAPER_EVIDENCE_GATE=" + json.dumps(H.RESULT, separators=(",", ":")), flush=True)
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), H).serve_forever()


if __name__ == "__main__":
    main()
