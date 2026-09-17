from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:
    psycopg = None
    dict_row = None


class Store:
    """Durable PAPER state + prospective audit store.

    PostgreSQL is used when DATABASE_URL is provided; otherwise SQLite.
    The SQL surface is intentionally kept portable between both backends.
    """

    def __init__(self, sqlite_path: str, database_url: str = ""):
        self.database_url = (database_url or "").strip()
        self.backend = "postgres" if self.database_url else "sqlite"
        self.sqlite_path = sqlite_path

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
            """
            CREATE TABLE IF NOT EXISTS decision_events(
              event_id TEXT PRIMARY KEY,
              symbol TEXT NOT NULL,
              close_ms BIGINT NOT NULL,
              decided_at TEXT NOT NULL,
              state TEXT,
              trend TEXT,
              breakout TEXT,
              action TEXT,
              price DOUBLE PRECISION,
              ema20_4h DOUBLE PRECISION,
              ema50_4h DOUBLE PRECISION,
              don_hi DOUBLE PRECISION,
              don_lo DOUBLE PRECISION,
              atr DOUBLE PRECISION,
              candidate_side TEXT,
              candidate_decision TEXT,
              payload TEXT
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

    def record_decision(self, strategy: str, symbol: str, close_ms: int, decided_at: str,
                        ctx: dict, candidate=None) -> bool:
        event_id = f"{strategy}:{symbol}:{int(close_ms)}"
        action = candidate.decision if candidate is not None else ctx.get("state", "UNKNOWN")
        payload = {
            "context": ctx,
            "candidate": candidate.__dict__ if candidate is not None else None,
        }
        cur = self._exec(
            """
            INSERT INTO decision_events(
              event_id,symbol,close_ms,decided_at,state,trend,breakout,action,price,
              ema20_4h,ema50_4h,don_hi,don_lo,atr,candidate_side,candidate_decision,payload
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(event_id) DO NOTHING
            """,
            (
                event_id, symbol, int(close_ms), decided_at,
                ctx.get("state"), ctx.get("trend"), ctx.get("breakout"), action,
                ctx.get("price"), ctx.get("ema20_4h"), ctx.get("ema50_4h"),
                ctx.get("don_hi"), ctx.get("don_lo"), ctx.get("atr"),
                getattr(candidate, "side", None), getattr(candidate, "decision", None),
                json.dumps(payload),
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

    def recent_decisions(self, n: int = 20):
        rows = self._exec(
            "SELECT * FROM decision_events ORDER BY close_ms DESC, symbol ASC LIMIT ?",
            (n,),
        ).fetchall()
        out=[]
        for r in rows:
            d=dict(r)
            d.pop("payload", None)
            out.append(d)
        return out

    def signal_count(self) -> int:
        r = self._exec("SELECT COUNT(*) AS n FROM signals").fetchone()
        return int(r["n"] if r else 0)

    def trade_count(self) -> int:
        r = self._exec("SELECT COUNT(*) AS n FROM trades").fetchone()
        return int(r["n"] if r else 0)

    def decision_count(self, symbol: str | None = None) -> int:
        if symbol:
            r=self._exec("SELECT COUNT(*) AS n FROM decision_events WHERE symbol=?",(symbol,)).fetchone()
        else:
            r=self._exec("SELECT COUNT(*) AS n FROM decision_events").fetchone()
        return int(r["n"] if r else 0)

    def last_decision(self, symbol: str):
        r=self._exec(
            "SELECT close_ms,decided_at FROM decision_events WHERE symbol=? ORDER BY close_ms DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        return dict(r) if r else None

    def daily_realized_pnl(self, now_ms: int) -> float:
        day=datetime.fromtimestamp(now_ms/1000,tz=timezone.utc).date()
        rows=self._exec("SELECT closed_ms,pnl FROM trades WHERE outcome!='OPEN' AND closed_ms IS NOT NULL").fetchall()
        total=0.0
        for r in rows:
            if datetime.fromtimestamp(int(r["closed_ms"])/1000,tz=timezone.utc).date()==day:
                total += float(r["pnl"] or 0)
        return total

    def audit_summary(self, cost: float, start_equity: float, now_ms: int) -> dict:
        rows=[dict(r) for r in self._exec(
            "SELECT * FROM trades WHERE outcome!='OPEN' AND closed_ms IS NOT NULL ORDER BY closed_ms,trade_id"
        ).fetchall()]
        rs=[]; cost_rs=[]; gross_rs=[]; total_pnl=0.0; wins=0
        cumulative=0.0; peak=0.0; max_dd=0.0
        for t in rows:
            r=float(t.get("r_net") or 0); rs.append(r); total_pnl+=float(t.get("pnl") or 0)
            if r>0:wins+=1
            risk=float(t.get("risk") or 0); qty=float(t.get("qty") or 0)
            fees=(float(t.get("entry") or 0)+float(t.get("exit") or 0))*qty*(cost/2)
            cr=fees/risk if risk else 0.0; cost_rs.append(cr); gross_rs.append(r+cr)
            cumulative+=r; peak=max(peak,cumulative); max_dd=max(max_dd,peak-cumulative)
        pos=sum(x for x in rs if x>0); neg=-sum(x for x in rs if x<0)
        n=len(rs)
        return {
            "decision_events":self.decision_count(),
            "breakout_candidates":self.signal_count(),
            "paper_trades_total":self.trade_count(),
            "closed_trades":n,
            "open_position":bool(self.open_trade()),
            "wins":wins,
            "losses":n-wins,
            "win_rate":wins/n if n else None,
            "expectancy_net_R":sum(rs)/n if n else None,
            "total_net_R":sum(rs) if n else 0.0,
            "profit_factor_net":pos/neg if neg>0 else None,
            "max_drawdown_R":-max_dd,
            "avg_cost_R":sum(cost_rs)/n if n else None,
            "avg_gross_R":sum(gross_rs)/n if n else None,
            "realized_pnl":total_pnl,
            "equity":start_equity+total_pnl,
            "daily_realized_pnl_utc":self.daily_realized_pnl(now_ms),
        }
