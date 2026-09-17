from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.request


SLOW_HEALTH_URL = "http://127.0.0.1:8081/healthz"
HEALTH_STARTUP_GRACE_S = 30
HEALTH_INTERVAL_S = 15
HEALTH_FAILURE_LIMIT = 3


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
    slow_health_failures = 0
    next_slow_health = time.time() + HEALTH_STARTUP_GRACE_S

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
    print(
        f"SUPERVISOR_STARTED slow_health={SLOW_HEALTH_URL} "
        f"grace_s={HEALTH_STARTUP_GRACE_S} interval_s={HEALTH_INTERVAL_S} "
        f"failure_limit={HEALTH_FAILURE_LIMIT}",
        flush=True,
    )

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

            now = time.time()
            if now >= next_slow_health:
                try:
                    with urllib.request.urlopen(SLOW_HEALTH_URL, timeout=5) as r:
                        if int(getattr(r, "status", 0)) != 200:
                            raise RuntimeError(f"HTTP {getattr(r, 'status', None)}")
                        r.read(256)
                    if slow_health_failures:
                        print("SUPERVISOR_SLOW_HEALTH_RECOVERED", flush=True)
                    slow_health_failures = 0
                except Exception as exc:
                    slow_health_failures += 1
                    print(
                        f"SUPERVISOR_SLOW_HEALTH_FAIL count={slow_health_failures} "
                        f"error={type(exc).__name__}:{exc}",
                        flush=True,
                    )
                    if slow_health_failures >= HEALTH_FAILURE_LIMIT:
                        print("SUPERVISOR_SLOW_UNHEALTHY_RESTART", flush=True)
                        stop_all()
                        return 1
                next_slow_health = now + HEALTH_INTERVAL_S

            time.sleep(1)
    finally:
        stop_all()


if __name__ == "__main__":
    raise SystemExit(main())
