"""SQLite: what was sent, saved, applied; settings changed from Telegram; stats."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Job, utcnow

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT UNIQUE NOT NULL,
    fingerprint TEXT NOT NULL,
    source TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',      -- unused; per-person marks live in user_jobs
    sent_at TEXT NOT NULL,
    chat_id TEXT, message_id INTEGER
);
CREATE INDEX IF NOT EXISTS jobs_fp ON jobs(fingerprint);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL);
-- each person's own Saved / Applied / Not-for-me marks
CREATE TABLE IF NOT EXISTS user_jobs (
    user_id INTEGER NOT NULL,
    job_id INTEGER NOT NULL,
    status TEXT NOT NULL,                     -- saved | applied | hidden
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, job_id)
);
CREATE INDEX IF NOT EXISTS user_jobs_status ON user_jobs(user_id, status);
"""


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # ---- dedupe ----
    def is_seen(self, job: Job) -> bool:
        row = self.db.execute("SELECT 1 FROM jobs WHERE uid=? OR fingerprint=? LIMIT 1",
                              (job.uid, job.fingerprint)).fetchone()
        return row is not None

    def record(self, job: Job, chat_id: str | None = None, message_id: int | None = None) -> int:
        cur = self.db.execute(
            "INSERT OR IGNORE INTO jobs(uid, fingerprint, source, payload, sent_at, chat_id, message_id)"
            " VALUES (?,?,?,?,?,?,?)",
            (job.uid, job.fingerprint, job.source, json.dumps(job.to_dict()),
             utcnow().isoformat(), chat_id, message_id))
        self.db.commit()
        if cur.lastrowid and cur.rowcount:
            return cur.lastrowid
        return self.db.execute("SELECT id FROM jobs WHERE uid=?", (job.uid,)).fetchone()["id"]

    def set_message(self, job_id: int, chat_id: str, message_id: int):
        self.db.execute("UPDATE jobs SET chat_id=?, message_id=? WHERE id=?", (chat_id, message_id, job_id))
        self.db.commit()

    # ---- statuses ----
    def get(self, job_id: int) -> tuple[Job, str] | None:
        row = self.db.execute("SELECT payload, status FROM jobs WHERE id=?", (job_id,)).fetchone()
        return (Job.from_dict(json.loads(row["payload"])), row["status"]) if row else None

    def recent(self, minutes: int = 60, limit: int = 10) -> list[tuple[int, Job]]:
        since = (utcnow() - timedelta(minutes=minutes)).isoformat()
        rows = self.db.execute("SELECT id, payload FROM jobs WHERE sent_at>=? AND status!='hidden' "
                               "ORDER BY sent_at DESC LIMIT ?", (since, limit)).fetchall()
        return [(r["id"], Job.from_dict(json.loads(r["payload"]))) for r in rows]

    # ---- per-user marks ----
    def user_status(self, user_id: int, job_id: int) -> str | None:
        row = self.db.execute("SELECT status FROM user_jobs WHERE user_id=? AND job_id=?",
                              (user_id, job_id)).fetchone()
        return row["status"] if row else None

    def set_user_status(self, user_id: int, job_id: int, status: str | None):
        if status is None:
            self.db.execute("DELETE FROM user_jobs WHERE user_id=? AND job_id=?", (user_id, job_id))
        else:
            self.db.execute(
                "INSERT INTO user_jobs(user_id, job_id, status, updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(user_id, job_id) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at",
                (user_id, job_id, status, utcnow().isoformat()))
        self.db.commit()

    def user_jobs(self, user_id: int, status: str, limit: int = 30) -> list[tuple[int, Job]]:
        rows = self.db.execute(
            "SELECT j.id, j.payload FROM user_jobs u JOIN jobs j ON j.id=u.job_id "
            "WHERE u.user_id=? AND u.status=? ORDER BY u.updated_at DESC LIMIT ?",
            (user_id, status, limit)).fetchall()
        return [(r["id"], Job.from_dict(json.loads(r["payload"]))) for r in rows]

    def job_counts(self, job_id: int) -> dict:
        rows = self.db.execute("SELECT status, COUNT(*) FROM user_jobs WHERE job_id=? GROUP BY status",
                               (job_id,)).fetchall()
        return {r[0]: r[1] for r in rows}

    def user_stats(self, user_id: int) -> dict:
        rows = self.db.execute("SELECT status, COUNT(*) FROM user_jobs WHERE user_id=? GROUP BY status",
                               (user_id,)).fetchall()
        return {r[0]: r[1] for r in rows}

    def stats(self) -> dict:
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        q = lambda sql, *a: self.db.execute(sql, a).fetchone()[0]
        per_source = dict(self.db.execute(
            "SELECT source, COUNT(*) FROM jobs WHERE sent_at>=? GROUP BY source ORDER BY 2 DESC",
            (today,)).fetchall())
        return {
            "total": q("SELECT COUNT(*) FROM jobs"),
            "today": q("SELECT COUNT(*) FROM jobs WHERE sent_at>=?", today),
            "saved": q("SELECT COUNT(*) FROM user_jobs WHERE status='saved'"),
            "applied": q("SELECT COUNT(*) FROM user_jobs WHERE status='applied'"),
            "people": q("SELECT COUNT(DISTINCT user_id) FROM user_jobs"),
            "per_source_today": per_source,
        }

    # ---- key/value (settings overrides, telegram offset) ----
    def kv_get(self, k: str, default=None):
        row = self.db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return json.loads(row["v"]) if row else default

    def kv_set(self, k: str, v):
        self.db.execute("INSERT INTO kv(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                        (k, json.dumps(v)))
        self.db.commit()
