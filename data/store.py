"""SQLite persistence (master plan §1.3). Tables: ohlcv, zones, signals, trades, runs.

OHLCV upserts are idempotent on (symbol, tf, ts) so re-fetching an overlapping
window never duplicates or corrupts bars (P0 acceptance gate).
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterable, List, Optional, Sequence, Tuple

from engine.candles import Candle

_DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "data", "sdz.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ohlcv (
    symbol TEXT NOT NULL,
    tf     TEXT NOT NULL,
    ts     INTEGER NOT NULL,      -- epoch ms, candle open time (UTC)
    open   REAL NOT NULL,
    high   REAL NOT NULL,
    low    REAL NOT NULL,
    close  REAL NOT NULL,
    volume REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, tf, ts)
);

CREATE TABLE IF NOT EXISTS zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    symbol TEXT, tf TEXT, ztype TEXT, pattern TEXT,
    proximal REAL, distal REAL,
    confirm_ts INTEGER, confirm_index INTEGER,
    base_len INTEGER, score INTEGER, state TEXT,
    breakdown TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER, symbol TEXT, tf TEXT, kind TEXT, payload TEXT
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER, zone_id INTEGER,
    symbol TEXT, tf TEXT, market TEXT, pattern TEXT,
    score INTEGER, freshness INTEGER,
    entry_ts INTEGER, exit_ts INTEGER,
    entry REAL, stop REAL, target REAL,
    exit_price REAL, outcome TEXT, r REAL,
    origin TEXT DEFAULT 'backtest'   -- backtest | paper | live
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_ts INTEGER, kind TEXT, params_json TEXT, notes TEXT
);
"""


class Store:
    def __init__(self, path: str = _DEFAULT_PATH):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- OHLCV -----------------------------------------------------------
    def upsert_ohlcv(self, symbol: str, tf: str,
                     rows: Iterable[Sequence[float]]) -> int:
        """rows: iterable of (ts, open, high, low, close, volume). Idempotent."""
        sql = (
            "INSERT INTO ohlcv (symbol, tf, ts, open, high, low, close, volume) "
            "VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(symbol, tf, ts) DO UPDATE SET "
            "open=excluded.open, high=excluded.high, low=excluded.low, "
            "close=excluded.close, volume=excluded.volume"
        )
        payload = [
            (symbol, tf, int(r[0]), float(r[1]), float(r[2]),
             float(r[3]), float(r[4]), float(r[5]) if len(r) > 5 else 0.0)
            for r in rows
        ]
        cur = self.conn.executemany(sql, payload)
        self.conn.commit()
        return len(payload)

    def load_candles(self, symbol: str, tf: str,
                     start_ts: Optional[int] = None,
                     end_ts: Optional[int] = None) -> List[Candle]:
        q = "SELECT ts,open,high,low,close,volume FROM ohlcv WHERE symbol=? AND tf=?"
        args: list = [symbol, tf]
        if start_ts is not None:
            q += " AND ts>=?"; args.append(start_ts)
        if end_ts is not None:
            q += " AND ts<=?"; args.append(end_ts)
        q += " ORDER BY ts ASC"
        rows = self.conn.execute(q, args).fetchall()
        return [Candle(r["ts"], r["open"], r["high"], r["low"], r["close"], r["volume"])
                for r in rows]

    def ohlcv_span(self, symbol: str, tf: str) -> Tuple[Optional[int], Optional[int], int]:
        row = self.conn.execute(
            "SELECT MIN(ts) lo, MAX(ts) hi, COUNT(*) n FROM ohlcv WHERE symbol=? AND tf=?",
            (symbol, tf),
        ).fetchone()
        return row["lo"], row["hi"], row["n"]

    # --- runs / trades / zones ------------------------------------------
    def new_run(self, created_ts: int, kind: str, params_json: str, notes: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (created_ts, kind, params_json, notes) VALUES (?,?,?,?)",
            (created_ts, kind, params_json, notes),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def insert_trade(self, **kw) -> int:
        cols = ",".join(kw.keys())
        ph = ",".join("?" for _ in kw)
        cur = self.conn.execute(
            f"INSERT INTO trades ({cols}) VALUES ({ph})", tuple(kw.values())
        )
        self.conn.commit()
        return int(cur.lastrowid)
