from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # psycopg is optional when SQLite fallback is used
    psycopg = None
    dict_row = None


class Store:
    """Small durable state store.

    Uses PostgreSQL when database_url is provided; otherwise SQLite.
    SQL is intentionally limited to constructs supported by both backends.
    """

    def __init__(self, sqlite_path: str, database_url: str = ""):
        self.database_url = (database_url or "").strip()
        self.backend = "postgres" if self.database_url else "sqlite"

        if self.backend == "postgres":
            if psycopg is None:
                raise RuntimeError("DATABASE_URL is set but psycopg is not installed")
            self.c = psycopg.connect(
                self.database_url,
                autocommit=True,
                row_factory=dict_row,
                connect_timeout=10,
            )
        else:
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
            self.c = sqlite3.connect(sqlite_path, check_same_thread=False)
            self.c.row_factory = sqlite3.Row
            self.c.execute("PRAGMA journal_mode=WAL")

        self._init_schema()

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.backend == "postgres" else sql

    def _exec(self, sql: str, params: tuple[Any, ...] = ()):
        return self.c.execute(self._sql(sql), params)

    def _commit(self):
        if self.backend == "sqlite":
            self.c.commit()

    def _init_schema(self):
        stmts = [
            """
            CREATE TABLE IF NOT EXISTS runtime_state(
              k TEXT PRIMARY KEY,
              v TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS signals(
              signal_id TEXT PRIMARY KEY,
              symbol TEXT,
              side TEXT,
              decision TEXT,
              signal_ms BIGINT,
              payload TEXT,
              created_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS trades(
              trade_id TEXT PRIMARY KEY,
              signal_id TEXT,
              symbol TEXT,
              side TEXT,
              entry DOUBLE PRECISION,
              stop DOUBLE PRECISION,
              target DOUBLE PRECISION,
              qty DOUBLE PRECISION,
              risk DOUBLE PRECISION,
              opened_ms BIGINT,
              last_check_ms BIGINT,
              closed_ms BIGINT,
              exit DOUBLE PRECISION,
              outcome TEXT,
              pnl DOUBLE PRECISION,
              r_net DOUBLE PRECISION
            )
            """,
        ]
        for stmt in stmts:
            self._exec(stmt)
        self._commit()

    def close_conn(self):
        try:
            self.c.close()
        except Exception:
            pass

    def get(self, k: str):
        r = self._exec("SELECT v FROM runtime_state WHERE k=?", (k,)).fetchone()
        return r["v"] if r else None

    def set(self, k: str, v: Any):
        self._exec(
            """
            INSERT INTO runtime_state(k,v) VALUES(?,?)
            ON CONFLICT(k) DO UPDATE SET v=excluded.v
            """,
            (k, str(v)),
        )
        self._commit()

    def get_int(self, k: str, default: int = 0) -> int:
        raw = self.get(k)
        try:
            return int(raw) if raw is not None else default
        except Exception:
            return default

    def open_trade(self):
        r = self._exec(
            "SELECT * FROM trades WHERE outcome='OPEN' ORDER BY opened_ms LIMIT 1"
        ).fetchone()
        return dict(r) if r else None

    def record_signal(self, p, created_at: str) -> bool:
        cur = self._exec(
            """
            INSERT INTO signals(signal_id,symbol,side,decision,signal_ms,payload,created_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(signal_id) DO NOTHING
            """,
            (
                p.signal_id,
                p.symbol,
                p.side,
                p.decision,
                p.signal_ms,
                json.dumps(p.__dict__),
                created_at,
            ),
        )
        self._commit()
        return cur.rowcount == 1

    def open_position(self, p, now_ms: int) -> bool:
        if self.open_trade():
            return False
        cur = self._exec(
            """
            INSERT INTO trades(
              trade_id,signal_id,symbol,side,entry,stop,target,qty,risk,
              opened_ms,last_check_ms,outcome,pnl,r_net
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0,0)
            ON CONFLICT(trade_id) DO NOTHING
            """,
            (
                "slow_" + p.signal_id,
                p.signal_id,
                p.symbol,
                p.side,
                p.entry,
                p.stop,
                p.target,
                p.qty,
                p.risk_usdt,
                now_ms,
                now_ms,
                "OPEN",
            ),
        )
        self._commit()
        return cur.rowcount == 1

    # Compatibility alias while staging code migrates.
    def open(self, p, now_ms: int) -> bool:
        return self.open_position(p, now_ms)

    def mark_checked(self, trade_id: str, ms: int):
        self._exec(
            "UPDATE trades SET last_check_ms=? WHERE trade_id=?",
            (ms, trade_id),
        )
        self._commit()

    def close(self, t: dict, px: float, outcome: str, closed_ms: int, cost: float):
        sg = 1 if t["side"] == "LONG" else -1
        gross = (px - t["entry"]) * sg * t["qty"]
        fees = (t["entry"] + px) * t["qty"] * (cost / 2)
        pnl = gross - fees
        r = pnl / t["risk"] if t["risk"] else 0
        self._exec(
            """
            UPDATE trades
            SET closed_ms=?,exit=?,outcome=?,pnl=?,r_net=?,last_check_ms=?
            WHERE trade_id=?
            """,
            (closed_ms, px, outcome, pnl, r, closed_ms, t["trade_id"]),
        )
        self._commit()

    def equity(self, start_equity: float) -> float:
        r = self._exec(
            "SELECT COALESCE(SUM(pnl),0) AS z FROM trades WHERE outcome!='OPEN'"
        ).fetchone()
        return start_equity + float(r["z"] or 0)

    def recent(self, n: int = 20):
        rows = self._exec(
            """
            SELECT * FROM trades
            ORDER BY COALESCE(closed_ms,opened_ms) DESC
            LIMIT ?
            """,
            (n,),
        ).fetchall()
        return [dict(r) for r in rows]

    def signal_count(self) -> int:
        r = self._exec("SELECT COUNT(*) AS n FROM signals").fetchone()
        return int(r["n"] if r else 0)

    def trade_count(self) -> int:
        r = self._exec("SELECT COUNT(*) AS n FROM trades").fetchone()
        return int(r["n"] if r else 0)
