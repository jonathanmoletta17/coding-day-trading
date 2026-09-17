from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


def main() -> int:
    port = os.getenv("PORT", "8080")
    env = os.environ.copy()
    env["MRC_STAGING_DB"] = "/data/mrc_slow_staging_v3.sqlite3"

    slow = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "slow_app_v2:app", "--host", "0.0.0.0", "--port", "8081"],
        env=env,
    )
    public = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "trend_v1:app", "--host", "0.0.0.0", "--port", port],
        env=os.environ.copy(),
    )

    children = (slow, public)
    stopping = False

    def stop_all(signum=None, frame=None):
        nonlocal stopping
        if stopping:
            return
        stopping = True
        for proc in children:
            if proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
        deadline = time.time() + 8
        for proc in children:
            while proc.poll() is None and time.time() < deadline:
                time.sleep(0.1)
            if proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass

    signal.signal(signal.SIGTERM, stop_all)
    signal.signal(signal.SIGINT, stop_all)

    try:
        while True:
            slow_rc = slow.poll()
            public_rc = public.poll()
            if slow_rc is not None or public_rc is not None:
                print(
                    f"SUPERVISOR_CHILD_EXIT slow_rc={slow_rc} public_rc={public_rc}",
                    flush=True,
                )
                stop_all()
                return 1
            time.sleep(1)
    finally:
        stop_all()


if __name__ == "__main__":
    raise SystemExit(main())
