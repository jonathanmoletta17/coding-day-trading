from __future__ import annotations

import math
import tempfile
from pathlib import Path
from types import SimpleNamespace

from slow_store_v3 import Store


def close_enough(a, b, tol=1e-10):
    return math.isclose(float(a), float(b), rel_tol=0, abs_tol=tol)


def main():
    with tempfile.TemporaryDirectory() as td:
        db=Store(str(Path(td)/"cost_test.sqlite3"))
        p=SimpleNamespace(
            signal_id="cost_case_1",symbol="BTCUSDT",side="LONG",decision="LONG",
            entry=100.0,stop=90.0,target=120.0,qty=1.0,risk_usdt=10.0,signal_ms=1000,
        )
        assert db.open(p,1001)
        t=db.open_trade();assert t is not None
        db.close(t,110.0,"TARGET",2000,0.0006)

        stored_before=db.recent(1)[0]
        base=db.audit_summary(0.0006,10000.0,3000)
        s=db.cost_sensitivity({"baseline_6bps":0.0006,"stress_10bps":0.0010,"stress_15bps":0.0015},10000.0)
        stored_after=db.recent(1)[0]

        # Gross PnL = 10. Round-trip fee = (100+110)*cost/2.
        expected={
            "baseline_6bps":(10.0-210.0*0.0003)/10.0,
            "stress_10bps":(10.0-210.0*0.0005)/10.0,
            "stress_15bps":(10.0-210.0*0.00075)/10.0,
        }
        for name,r in expected.items():
            assert close_enough(s[name]["expectancy_net_R"],r),(name,s[name],r)
            assert s[name]["closed_trades"]==1
            assert close_enough(s[name]["avg_gross_R"],1.0)

        # The 6 bps scenario must reproduce the persisted 6 bps result exactly.
        assert close_enough(s["baseline_6bps"]["expectancy_net_R"],base["expectancy_net_R"])
        assert close_enough(s["baseline_6bps"]["realized_pnl"],base["realized_pnl"])

        # Audit repricing is read-only.
        assert stored_before["pnl"]==stored_after["pnl"]
        assert stored_before["r_net"]==stored_after["r_net"]
        db.close_conn()

    print("SLOW_COST_SENSITIVITY_TEST=PASS scenarios=6bps,10bps,15bps non_mutating=true")


if __name__=="__main__":main()
