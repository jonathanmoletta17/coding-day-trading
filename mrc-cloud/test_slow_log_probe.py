import hashlib
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

import slow_log_probe as probe


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_hash_chain_detects_tampering():
    with TemporaryDirectory() as td:
        chain = Path(td) / "evidence.ndjson"
        first = probe.append_chain_record(chain, "STATE", {"decisions": 10})
        second = probe.append_chain_record(chain, "STATE", {"decisions": 12})
        verified = probe.verify_chain(chain)
        assert verified["ok"] is True
        assert verified["records"] == 2
        assert verified["head"] == second["record_hash"]
        assert first["record_hash"] != second["record_hash"]

        lines = chain.read_text(encoding="utf-8").splitlines()
        record = json.loads(lines[0])
        record["payload"]["decisions"] = 999
        lines[0] = json.dumps(record, sort_keys=True, separators=(",", ":"))
        chain.write_text("\n".join(lines) + "\n", encoding="utf-8")
        broken = probe.verify_chain(chain)
        assert broken["ok"] is False
        assert "RECORD_HASH_MISMATCH" in broken["error"]


def test_sqlite_backup_is_consistent_and_source_is_unchanged():
    with TemporaryDirectory() as td:
        root = Path(td)
        source = root / "paper.sqlite3"
        connection = sqlite3.connect(source)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE evidence(id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO evidence(value) VALUES('first-trade')")
        connection.commit()
        connection.close()
        before = file_hash(source)

        old_root, old_manifest = probe.BACKUP_ROOT, probe.BACKUP_MANIFEST
        try:
            probe.BACKUP_ROOT = root / "backups"
            probe.BACKUP_MANIFEST = probe.BACKUP_ROOT / "backup_manifest_chain.ndjson"
            result = probe.backup_sqlite(source, "TEST")
        finally:
            probe.BACKUP_ROOT, probe.BACKUP_MANIFEST = old_root, old_manifest

        assert file_hash(source) == before
        backup = root / "backups" / result["backup_file"]
        assert backup.is_file()
        assert result["sqlite_quick_check"] == "ok"
        assert result["sha256"] == file_hash(backup)
        restored = sqlite3.connect(backup)
        try:
            assert restored.execute("SELECT value FROM evidence").fetchone()[0] == "first-trade"
        finally:
            restored.close()
        manifest = probe.verify_chain(root / "backups" / "backup_manifest_chain.ndjson")
        assert manifest["ok"] is True
        assert manifest["records"] == 1


def test_meaningful_summary_tracks_only_audit_state():
    ready = {"ready": True, "last_error": None, "coverage_gap": None}
    evidence = {"evidence_quality": {"integrity_pass": True, "decision_events_total": 126, "signals_total": 2,
                                     "paper_trades_total": 1, "closed_paper_trades": 1, "open_paper_trades": 0}}
    audit = {"release_sha": "release", "prospective": {"equity": 9973.93, "total_net_R": -1.0428}}
    science = {"scientific_readiness": {"status": "INSUFFICIENT_EVIDENCE", "evidence_floor_met": False}}
    reviews = {"closed_trade_reviews": {"all_link_integrity_pass": True}}
    out = probe.meaningful_summary(ready, evidence, audit, science, reviews)
    assert out["decision_events"] == 126
    assert out["closed_trades"] == 1
    assert out["scientific_floor_met"] is False
    assert out["all_closed_trade_links_pass"] is True


def run_all():
    tests = [
        test_hash_chain_detects_tampering,
        test_sqlite_backup_is_consistent_and_source_is_unchanged,
        test_meaningful_summary_tracks_only_audit_state,
    ]
    for fn in tests:
        fn()
    print(f"SLOW_EVIDENCE_ARCHIVE_TEST=PASS cases={len(tests)} tamper_evident=true sqlite_backup=true")


if __name__ == "__main__":
    run_all()
