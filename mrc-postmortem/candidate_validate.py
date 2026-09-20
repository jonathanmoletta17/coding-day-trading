from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import urlretrieve

SHA="c4ce29173d08b3c5a8e030b1bd6de361068ee2fa"
BASE=f"https://raw.githubusercontent.com/jonathanmoletta17/coding-day-trading/{SHA}/mrc-cloud/"
TOOL_SHA="83c7760660ba2a9633f572b5661b61e8feda6e1c"
TOOL_BASE=f"https://raw.githubusercontent.com/jonathanmoletta17/coding-day-trading/{TOOL_SHA}/mrc-research/"
FILES=(
    "slow_engine_v2.py","slow_store_v3.py","slow_replay_v1.py","slow_execution_adapter_v1.py",
    "slow_okx_demo_diagnostic_v1.py","slow_evidence_v1.py","slow_app_v2.py",
    "test_slow_engine_v2.py","test_slow_restart_replay_v1.py","test_slow_execution_adapter_v1.py",
    "test_slow_okx_demo_diagnostic_v1.py","test_slow_cost_sensitivity_v1.py","test_slow_evidence_v1.py",
)
TESTS=(
    "test_slow_engine_v2.py","test_slow_restart_replay_v1.py","test_slow_execution_adapter_v1.py",
    "test_slow_okx_demo_diagnostic_v1.py","test_slow_cost_sensitivity_v1.py","test_slow_evidence_v1.py",
)


def main()->None:
    with tempfile.TemporaryDirectory(prefix="mrc-candidate-") as td:
        root=Path(td)
        for name in FILES:urlretrieve(BASE+name,root/name)
        subprocess.run([sys.executable,"-m","py_compile","slow_app_v2.py","slow_evidence_v1.py"],cwd=root,check=True)
        for name in TESTS:subprocess.run([sys.executable,name],cwd=root,check=True)
    for name in ("first_trade_postmortem.py","test_first_trade_postmortem.py"):
        urlretrieve(TOOL_BASE+name,Path.cwd()/name)
    print(f"PAPER_OBSERVABILITY_CANDIDATE_VALIDATED={SHA}",flush=True)


if __name__=="__main__":main()
