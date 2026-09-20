from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

URL = os.getenv("MRC_PAPER_LOCAL_BASE", "http://127.0.0.1:8081").rstrip("/")
POLL_SECONDS = max(30, int(os.getenv("MRC_ARCHIVE_POLL_SECONDS", "300")))
HEARTBEAT_SECONDS = max(900, int(os.getenv("MRC_ARCHIVE_HEARTBEAT_SECONDS", "3600")))
BACKUP_SECONDS = max(3600, int(os.getenv("MRC_BACKUP_SECONDS", "86400")))
BACKUP_RETENTION = max(8, min(256, int(os.getenv("MRC_BACKUP_RETENTION", "64"))))
DB_PATH = Path(os.getenv("MRC_STAGING_DB", "/data/mrc_slow_staging_v3.sqlite3"))
ARCHIVE_ROOT = Path(os.getenv("MRC_EVIDENCE_ARCHIVE_ROOT", "/data/evidence"))
BACKUP_ROOT = Path(os.getenv("MRC_BACKUP_ROOT", "/data/backups"))
SNAPSHOT_CHAIN = ARCHIVE_ROOT / "paper_evidence_chain.ndjson"
BACKUP_MANIFEST = BACKUP_ROOT / "backup_manifest_chain.ndjson"
HEALTH_PATH = ARCHIVE_ROOT / "archive_health.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def verify_chain(path: Path) -> dict:
    if not path.exists():
        return {"ok": True, "records": 0, "head": "0" * 64}
    previous = "0" * 64
    records = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except Exception as exc:
                return {"ok": False, "records": records, "head": previous, "error": f"line={line_number} JSON {type(exc).__name__}: {exc}"}
            supplied = str(record.pop("record_hash", ""))
            expected = hashlib.sha256(canonical_bytes(record)).hexdigest()
            if record.get("prev_hash") != previous:
                return {"ok": False, "records": records, "head": previous, "error": f"line={line_number} PREV_HASH_MISMATCH"}
            if supplied != expected:
                return {"ok": False, "records": records, "head": previous, "error": f"line={line_number} RECORD_HASH_MISMATCH"}
            previous = supplied
            records += 1
    return {"ok": True, "records": records, "head": previous}


def append_chain_record(path: Path, kind: str, payload: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(Path(str(path) + ".lock")):
        state = verify_chain(path)
        if not state.get("ok"):
            raise RuntimeError(f"ARCHIVE_CHAIN_INVALID {state.get('error')}")
        record = {
            "seq": int(state["records"]) + 1,
            "captured_at": utc_now(),
            "kind": str(kind),
            "prev_hash": state["head"],
            "payload": payload,
        }
        record_hash = hashlib.sha256(canonical_bytes(record)).hexdigest()
        stored = {**record, "record_hash": record_hash}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(stored, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return {"seq": record["seq"], "record_hash": record_hash, "captured_at": record["captured_at"]}


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def backup_sqlite(source: Path, reason: str) -> dict:
    if not source.is_file():
        raise FileNotFoundError(f"PAPER_DB_NOT_FOUND {source}")
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(BACKUP_ROOT / ".backup.lock"):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destination = BACKUP_ROOT / f"mrc_slow_staging_v3_{stamp}.sqlite3"
        src = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=30)
        dst = sqlite3.connect(str(destination), timeout=30)
        try:
            src.backup(dst)
            check = dst.execute("PRAGMA quick_check").fetchone()
            quick_check = str(check[0]) if check else "missing"
        finally:
            dst.close()
            src.close()
        if quick_check.lower() != "ok":
            destination.unlink(missing_ok=True)
            raise RuntimeError(f"BACKUP_QUICK_CHECK_FAILED {quick_check}")
        entry = {
            "reason": str(reason),
            "source": str(source),
            "backup_file": destination.name,
            "size_bytes": destination.stat().st_size,
            "sha256": sha256_file(destination),
            "sqlite_quick_check": quick_check,
        }
        manifest = append_chain_record(BACKUP_MANIFEST, "SQLITE_BACKUP", entry)
        backups = sorted(BACKUP_ROOT.glob("mrc_slow_staging_v3_*.sqlite3"), key=lambda item: item.name)
        for old in backups[:-BACKUP_RETENTION]:
            old.unlink(missing_ok=True)
        return {**entry, "manifest_record_hash": manifest["record_hash"], "captured_at": manifest["captured_at"]}


def meaningful_summary(ready: dict, evidence: dict, audit: dict, science: dict, reviews: dict) -> dict:
    quality = evidence.get("evidence_quality") or {}
    prospective = audit.get("prospective") or {}
    scientific = science.get("scientific_readiness") or {}
    closed_reviews = reviews.get("closed_trade_reviews") or {}
    return {
        "release_sha": audit.get("release_sha"),
        "ready": ready.get("ready"),
        "last_error": ready.get("last_error"),
        "coverage_gap": ready.get("coverage_gap"),
        "evidence_integrity_pass": quality.get("integrity_pass"),
        "decision_events": quality.get("decision_events_total"),
        "signals": quality.get("signals_total"),
        "paper_trades": quality.get("paper_trades_total"),
        "closed_trades": quality.get("closed_paper_trades"),
        "open_trades": quality.get("open_paper_trades"),
        "equity": prospective.get("equity"),
        "total_net_R": prospective.get("total_net_R"),
        "scientific_status": scientific.get("status"),
        "scientific_floor_met": scientific.get("evidence_floor_met"),
        "all_closed_trade_links_pass": closed_reviews.get("all_link_integrity_pass"),
    }


def archive_payload(ready: dict, evidence: dict, audit: dict, costs: dict, science: dict, reviews: dict) -> dict:
    audit_copy = dict(audit)
    audit_copy.pop("archive_health", None)
    return {
        "summary": meaningful_summary(ready, evidence, audit_copy, science, reviews),
        "ready": ready,
        "evidence": evidence,
        "audit": audit_copy,
        "costs": costs,
        "scientific_readiness": science,
        "closed_trade_reviews": reviews,
    }


async def fetch_json(client, path: str) -> dict:
    response = await client.get(URL + path)
    response.raise_for_status()
    return response.json()


async def main():
    import httpx

    last_fingerprint = None
    last_snapshot_epoch = 0.0
    last_backup_epoch = 0.0
    last_closed_trades = None
    last_snapshot = None
    last_backup = None
    last_error = None
    ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=20.0) as client:
        while True:
            now = time.time()
            try:
                ready, evidence, audit, costs, science, reviews = await asyncio.gather(
                    fetch_json(client, "/readyz"),
                    fetch_json(client, "/api/evidence"),
                    fetch_json(client, "/api/audit"),
                    fetch_json(client, "/api/cost-sensitivity"),
                    fetch_json(client, "/api/scientific-readiness"),
                    fetch_json(client, "/api/closed-trade-reviews"),
                )
                payload = archive_payload(ready, evidence, audit, costs, science, reviews)
                summary = payload["summary"]
                fingerprint = hashlib.sha256(canonical_bytes(summary)).hexdigest()
                state_changed = fingerprint != last_fingerprint
                heartbeat_due = now - last_snapshot_epoch >= HEARTBEAT_SECONDS
                if state_changed or heartbeat_due:
                    kind = "PAPER_STATE_CHANGE" if state_changed else "PAPER_HEARTBEAT"
                    stored_payload = payload if state_changed else {"summary": summary, "fingerprint": fingerprint}
                    last_snapshot = append_chain_record(SNAPSHOT_CHAIN, kind, stored_payload)
                    last_snapshot_epoch = now
                    last_fingerprint = fingerprint

                closed_trades = int(summary.get("closed_trades") or 0)
                backup_reason = None
                if last_backup is None:
                    backup_reason = "STARTUP"
                elif last_closed_trades is not None and closed_trades != last_closed_trades:
                    backup_reason = "CLOSED_TRADE_COUNT_CHANGED"
                elif now - last_backup_epoch >= BACKUP_SECONDS:
                    backup_reason = "DAILY"
                if backup_reason:
                    last_backup = backup_sqlite(DB_PATH, backup_reason)
                    last_backup_epoch = now
                last_closed_trades = closed_trades
                last_error = None
                out = {**summary, "archive_fingerprint": fingerprint}
                print("SLOW_EVIDENCE_ARCHIVE=" + json.dumps(out, separators=(",", ":"), default=str), flush=True)
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                try:
                    last_snapshot = append_chain_record(SNAPSHOT_CHAIN, "ARCHIVE_INCIDENT", {"error": last_error, "url": URL})
                except Exception:
                    pass
                print(f"SLOW_EVIDENCE_ARCHIVE_ERROR={last_error}", flush=True)

            chain = verify_chain(SNAPSHOT_CHAIN)
            backup_chain = verify_chain(BACKUP_MANIFEST)
            health = {
                "version": "PAPER_EVIDENCE_ARCHIVE_V1",
                "heartbeat_at": utc_now(),
                "heartbeat_epoch": time.time(),
                "chain_ok": bool(chain.get("ok") and backup_chain.get("ok")),
                "snapshot_records": chain.get("records"),
                "last_snapshot_hash": chain.get("head") if chain.get("records") else None,
                "backup_manifest_records": backup_chain.get("records"),
                "last_backup_sha256": (last_backup or {}).get("sha256"),
                "last_backup_file": (last_backup or {}).get("backup_file"),
                "last_backup_quick_check": (last_backup or {}).get("sqlite_quick_check"),
                "last_error": last_error,
                "paper_database_mutated": False,
                "strategy_parameters_mutated": False,
            }
            atomic_json(HEALTH_PATH, health)
            await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
