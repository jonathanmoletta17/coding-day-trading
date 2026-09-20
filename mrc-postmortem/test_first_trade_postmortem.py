from __future__ import annotations

import sys
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]/"mrc-research"
if str(SOURCE) not in sys.path:sys.path.insert(0,str(SOURCE))

from test_first_trade_postmortem import run_all  # noqa: E402

if __name__=="__main__":run_all()
