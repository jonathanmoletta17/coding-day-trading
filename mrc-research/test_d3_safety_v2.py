from __future__ import annotations

import asyncio
import os

import d3_okx_demo_roundtrip as d3

KEYS = (
    "MRC_EXECUTION_MODE",
    "MRC_DEMO_EXECUTION_ENABLED",
    "MRC_KILL_SWITCH",
    "MRC_DEMO_DIAGNOSTIC_ONLY",
    "MRC_D3_ARM",
    "MRC_D3_ATTEMPT_ID",
    "MRC_D3_EXPECTED_LEVERAGE",
)


def set_env(**values: str) -> None:
    for key in KEYS:
        os.environ.pop(key, None)
    for key, value in values.items():
        os.environ[key] = value


async def expect_pre_network_gate(expected: str, **env: str) -> None:
    set_env(**env)
    try:
        # None is deliberate: every case below MUST fail before touching a Client.
        await d3.validate_preflight(None)  # type: ignore[arg-type]
    except RuntimeError as exc:
        if str(exc) != expected:
            raise AssertionError(f"expected {expected!r}, got {str(exc)!r}") from exc
    else:
        raise AssertionError(f"expected gate {expected!r} to abort")


async def main() -> None:
    saved = {k: os.environ.get(k) for k in KEYS}
    try:
        attempt = "D3SAFE001"
        ids1 = {kind: d3.deterministic_client_id(attempt, kind) for kind in ("OPEN", "CLOSE", "SAFE")}
        ids2 = {kind: d3.deterministic_client_id(attempt, kind) for kind in ("OPEN", "CLOSE", "SAFE")}
        assert ids1 == ids2
        assert len(set(ids1.values())) == 3
        assert all(1 <= len(x) <= 32 for x in ids1.values())

        cleanup = await d3.emergency_cleanup_owned_position(None, attempt, False)  # type: ignore[arg-type]
        assert cleanup == {"needed": False, "reason": "OPEN_SUBMISSION_NOT_ATTEMPTED"}

        await expect_pre_network_gate("MODE_NOT_DEMO")
        await expect_pre_network_gate(
            "DEMO_EXECUTION_NOT_ENABLED",
            MRC_EXECUTION_MODE="DEMO",
            MRC_DEMO_EXECUTION_ENABLED="0",
        )
        await expect_pre_network_gate(
            "KILL_SWITCH_ACTIVE",
            MRC_EXECUTION_MODE="DEMO",
            MRC_DEMO_EXECUTION_ENABLED="1",
            MRC_KILL_SWITCH="1",
        )
        await expect_pre_network_gate(
            "DIAGNOSTIC_ONLY_ACTIVE",
            MRC_EXECUTION_MODE="DEMO",
            MRC_DEMO_EXECUTION_ENABLED="1",
            MRC_KILL_SWITCH="0",
            MRC_DEMO_DIAGNOSTIC_ONLY="1",
        )
        await expect_pre_network_gate(
            "D3_NOT_ARMED_V2",
            MRC_EXECUTION_MODE="DEMO",
            MRC_DEMO_EXECUTION_ENABLED="1",
            MRC_KILL_SWITCH="0",
            MRC_DEMO_DIAGNOSTIC_ONLY="0",
            MRC_D3_ARM="DEMO_BTC_MIN_ROUNDTRIP_V1",
        )
        await expect_pre_network_gate(
            "D3_ATTEMPT_ID_INVALID",
            MRC_EXECUTION_MODE="DEMO",
            MRC_DEMO_EXECUTION_ENABLED="1",
            MRC_KILL_SWITCH="0",
            MRC_DEMO_DIAGNOSTIC_ONLY="0",
            MRC_D3_ARM=d3.ARM,
            MRC_D3_ATTEMPT_ID="bad",
        )
        await expect_pre_network_gate(
            "EXPECTED_LEVERAGE_NOT_DECLARED",
            MRC_EXECUTION_MODE="DEMO",
            MRC_DEMO_EXECUTION_ENABLED="1",
            MRC_KILL_SWITCH="0",
            MRC_DEMO_DIAGNOSTIC_ONLY="0",
            MRC_D3_ARM=d3.ARM,
            MRC_D3_ATTEMPT_ID=attempt,
        )

        print(
            "D3_SAFETY_V2_SELFTEST=PASS "
            f"arm={d3.ARM} deterministic_ids=true pre_network_gates=true cleanup_preopen_noop=true",
            flush=True,
        )
    finally:
        for key in KEYS:
            os.environ.pop(key, None)
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value


if __name__ == "__main__":
    asyncio.run(main())
