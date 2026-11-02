"""Small SQLite store: run history, listing cache, and verdict memory."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .types import Listing, Verdict

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    feed TEXT NOT NULL,
    mode TEXT NOT NULL,
    model TEXT,
    listings_seen INTEGER DEFAULT 0,
    listings_kept INTEGER DEFAULT 0,
    verdicts_cached INTEGER DEFAULT 0,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS listings (
    ref TEXT PRIMARY KEY,
    source TEXT,
    title TEXT,
    url TEXT,
    reward_usd REAL,
    currency TEXT,
    network TEXT,
    deadline TEXT,
    requires_json TEXT,
    fingerprint TEXT,
    first_seen TEXT,
    last_seen TEXT
);
CREATE TABLE IF NOT EXISTS verdicts (
    ref TEXT NOT NULL,
    run_id INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'live',
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (ref, run_id)
);
CREATE INDEX IF NOT EXISTS idx_verdicts_ref ON verdicts(ref, created_at DESC);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fingerprint(listing: Listing) -> str:
    payload = json.dumps(
        {
            "title": listing.title,
            "reward": listing.reward_usd,
            "requires": sorted(listing.requires),
            "deadline": listing.deadline.isoformat() if listing.deadline else None,
            "url": listing.url,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class Store:
    def __init__(self, path: str | Path = "data/scout.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def upsert_listings(self, listings: Iterable[Listing]) -> None:
        for item in listings:
            self.conn.execute(
                """
                INSERT INTO listings (ref, source, title, url, reward_usd, currency, network,
                                      deadline, requires_json, fingerprint, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ref) DO UPDATE SET
                    title=excluded.title, url=excluded.url, reward_usd=excluded.reward_usd,
                    currency=excluded.currency, network=excluded.network, deadline=excluded.deadline,
                    requires_json=excluded.requires_json, fingerprint=excluded.fingerprint,
                    last_seen=excluded.last_seen
                """,
                (
                    item.ref,
                    item.source,
                    item.title,
                    item.url,
                    item.reward_usd,
                    item.currency,
                    item.network,
                    item.deadline.isoformat() if item.deadline else None,
                    json.dumps(item.requires),
                    fingerprint(item),
                    item.first_seen or _now(),
                    _now(),
                ),
            )
        self.conn.commit()

    def cached_verdict(
        self, listing: Listing, max_age_seconds: int = 7 * 86400, mode: str = "live"
    ) -> Optional[Verdict]:
        row = self.conn.execute(
            "SELECT payload_json, created_at FROM verdicts WHERE ref=? AND mode=? "
            "ORDER BY created_at DESC LIMIT 1",
            (listing.ref, mode),
        ).fetchone()
        if not row:
            return None
        try:
            age = (
                datetime.now(timezone.utc) - datetime.fromisoformat(row["created_at"])
            ).total_seconds()
        except ValueError:
            return None
        if age > max_age_seconds:
            return None
        payload = json.loads(row["payload_json"])
        if payload.get("fingerprint") != fingerprint(listing):
            return None
        return Verdict.model_validate(payload["verdict"])

    def save_verdict(self, run_id: int, listing: Listing, verdict: Verdict, mode: str = "live") -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO verdicts (ref, run_id, fingerprint, mode, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                listing.ref,
                run_id,
                fingerprint(listing),
                mode,
                json.dumps({"fingerprint": fingerprint(listing), "verdict": verdict.model_dump()}),
                _now(),
            ),
        )
        self.conn.commit()

    def start_run(self, feed: str, mode: str, model: str) -> int:
        cursor = self.conn.execute(
            "INSERT INTO runs (started_at, feed, mode, model) VALUES (?, ?, ?, ?)",
            (_now(), feed, mode, model),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def finish_run(self, run_id: int, *, seen: int, kept: int, cached: int, notes: str = "") -> None:
        self.conn.execute(
            "UPDATE runs SET finished_at=?, listings_seen=?, listings_kept=?, verdicts_cached=?, notes=? "
            "WHERE id=?",
            (_now(), seen, kept, cached, notes, run_id),
        )
        self.conn.commit()

    def recent_runs(self, limit: int = 10) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        )
