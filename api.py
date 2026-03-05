"""
GoonZu Farm API
FastAPI server - drops + session management.
"""

import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

DB_NAME = "goonzu_farm.db"


# ── DB init ────────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS drops (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT    NOT NULL,
            item        TEXT    NOT NULL,
            qty         INTEGER NOT NULL,
            price_value REAL    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT    NOT NULL,
            ended_at   TEXT,
            status     TEXT    NOT NULL DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS session_pauses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL,
            paused_at   TEXT    NOT NULL,
            resumed_at  TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
    """)
    conn.commit()
    conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="GoonZu Farm", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


# ── Redirect ───────────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/static/index.html")


# ── Drops ──────────────────────────────────────────────────────────────────────
@app.get("/api/drops")
def recent_drops(limit: int = 100):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, ts, item, qty, price_value, qty * price_value AS total_value "
        "FROM drops ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/summary")
def summary(hours: int = 0):
    conn = get_db()
    where = "WHERE SUBSTR(ts,1,19) >= datetime('now',?)" if hours > 0 else ""
    params = (f"-{hours} hours",) if hours > 0 else ()
    rows = conn.execute(f"""
        SELECT item,
               SUM(qty)               AS total_qty,
               SUM(qty * price_value) AS total_value,
               COUNT(*)               AS drop_count,
               AVG(price_value)       AS avg_unit_price
        FROM drops {where}
        GROUP BY item ORDER BY total_value DESC
    """, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/stats")
def stats():
    conn = get_db()
    today = conn.execute("""
        SELECT COUNT(*) AS drop_events,
               COALESCE(SUM(qty), 0)               AS total_qty,
               COALESCE(SUM(qty * price_value), 0) AS total_value
        FROM drops WHERE SUBSTR(ts,1,10) >= date('now')
    """).fetchone()
    all_time = conn.execute("""
        SELECT COUNT(*) AS drop_events,
               COALESCE(SUM(qty * price_value), 0) AS total_value
        FROM drops
    """).fetchone()
    conn.close()
    return {"today": dict(today), "all_time": dict(all_time)}


@app.get("/api/timeline")
def timeline(hours: int = 6):
    conn = get_db()
    rows = conn.execute("""
        SELECT strftime('%Y-%m-%dT%H:00', SUBSTR(ts,1,19)) AS hour,
               SUM(qty * price_value) AS total_value,
               COUNT(*)               AS drop_events
        FROM drops
        WHERE SUBSTR(ts,1,19) >= datetime('now', ?)
        GROUP BY hour ORDER BY hour
    """, (f"-{hours} hours",)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Session helpers ────────────────────────────────────────────────────────────
FMT = "%Y-%m-%dT%H:%M:%S"


def _compute_active_seconds(session: dict, pauses: list[dict]) -> float:
    now   = datetime.now(timezone.utc).replace(tzinfo=None)
    start = datetime.strptime(session["started_at"][:19], FMT)
    end_s = session["ended_at"]
    end   = datetime.strptime(end_s[:19], FMT) if end_s else now

    total = (end - start).total_seconds()
    for p in pauses:
        ps = datetime.strptime(p["paused_at"][:19], FMT)
        pe_s = p["resumed_at"]
        pe = datetime.strptime(pe_s[:19], FMT) if pe_s else (
            now if session["status"] == "paused" else end
        )
        total -= (pe - ps).total_seconds()

    return max(0.0, total)


def _is_in_pause(ts_str: str, pauses: list[dict]) -> bool:
    try:
        dt = datetime.strptime(ts_str[:19], FMT)
    except ValueError:
        return False
    for p in pauses:
        ps = datetime.strptime(p["paused_at"][:19], FMT)
        pe_s = p["resumed_at"]
        pe = datetime.strptime(pe_s[:19], FMT) if pe_s else datetime.now()
        if ps <= dt <= pe:
            return True
    return False


# ── Session CRUD ───────────────────────────────────────────────────────────────
@app.post("/api/sessions/start")
def start_session():
    conn = get_db()
    now  = now_iso()
    conn.execute(
        "UPDATE sessions SET status='ended', ended_at=? WHERE status IN ('active','paused')", (now,)
    )
    conn.execute(
        "UPDATE session_pauses SET resumed_at=? WHERE resumed_at IS NULL", (now,)
    )
    conn.execute("INSERT INTO sessions (started_at, status) VALUES (?, 'active')", (now,))
    sid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return {"session_id": sid, "started_at": now}


@app.post("/api/sessions/{session_id}/pause")
def pause_session(session_id: int):
    conn = get_db()
    now  = now_iso()
    n = conn.execute(
        "UPDATE sessions SET status='paused' WHERE id=? AND status='active'", (session_id,)
    ).rowcount
    if not n:
        conn.close()
        raise HTTPException(400, "Session not active")
    conn.execute(
        "INSERT INTO session_pauses (session_id, paused_at) VALUES (?,?)", (session_id, now)
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/sessions/{session_id}/resume")
def resume_session(session_id: int):
    conn = get_db()
    now  = now_iso()
    n = conn.execute(
        "UPDATE sessions SET status='active' WHERE id=? AND status='paused'", (session_id,)
    ).rowcount
    if not n:
        conn.close()
        raise HTTPException(400, "Session not paused")
    conn.execute(
        "UPDATE session_pauses SET resumed_at=? WHERE session_id=? AND resumed_at IS NULL",
        (now, session_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/sessions/{session_id}/end")
def end_session(session_id: int):
    conn = get_db()
    now  = now_iso()
    conn.execute(
        "UPDATE sessions SET status='ended', ended_at=? WHERE id=?", (now, session_id)
    )
    conn.execute(
        "UPDATE session_pauses SET resumed_at=? WHERE session_id=? AND resumed_at IS NULL",
        (now, session_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/sessions/active")
def active_session():
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM sessions WHERE status IN ('active','paused') ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


@app.get("/api/sessions")
def list_sessions():
    conn = get_db()
    rows = conn.execute("""
        SELECT s.id, s.started_at, s.ended_at, s.status,
               COALESCE(SUM(d.qty * d.price_value), 0) AS total_value,
               COUNT(d.id)                              AS drop_events
        FROM sessions s
        LEFT JOIN drops d
               ON SUBSTR(d.ts,1,19) >= s.started_at
              AND (s.ended_at IS NULL OR SUBSTR(d.ts,1,19) <= s.ended_at)
        GROUP BY s.id
        ORDER BY s.id DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Session analytics ──────────────────────────────────────────────────────────
@app.get("/api/sessions/{session_id}/stats")
def session_stats(session_id: int):
    conn = get_db()
    session = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not session:
        conn.close()
        raise HTTPException(404, "Session not found")
    session = dict(session)
    pauses  = [dict(r) for r in conn.execute(
        "SELECT * FROM session_pauses WHERE session_id=?", (session_id,)
    ).fetchall()]

    start = session["started_at"]
    end   = session["ended_at"] or now_iso()

    all_drops = [dict(r) for r in conn.execute("""
        SELECT qty, price_value, SUBSTR(ts,1,19) AS ts_clean
        FROM drops
        WHERE SUBSTR(ts,1,19) >= ? AND SUBSTR(ts,1,19) <= ?
        ORDER BY ts_clean
    """, (start, end)).fetchall()]
    conn.close()

    # Filter out drops that happened during pauses
    active_drops = [d for d in all_drops if not _is_in_pause(d["ts_clean"], pauses)]

    total_value  = sum(d["qty"] * d["price_value"] for d in active_drops)
    drop_events  = len(active_drops)
    total_qty    = sum(d["qty"] for d in active_drops)
    active_secs  = _compute_active_seconds(session, pauses)
    active_hours = active_secs / 3600 if active_secs > 0 else 0
    avg_per_hour = total_value / active_hours if active_hours > 0 else 0

    # Moving avg: value dropped in last 15 min × 4 → projected hourly rate
    cutoff = (datetime.now() - timedelta(minutes=15)).strftime(FMT)
    recent_val = sum(
        d["qty"] * d["price_value"] for d in active_drops if d["ts_clean"] >= cutoff
    )
    moving_avg_h = recent_val * 4

    return {
        "session":        session,
        "active_seconds": round(active_secs),
        "total_value":    total_value,
        "drop_events":    drop_events,
        "total_qty":      total_qty,
        "avg_per_hour":   round(avg_per_hour),
        "moving_avg_h":   round(moving_avg_h),
    }


@app.get("/api/sessions/{session_id}/summary")
def session_summary(session_id: int):
    conn = get_db()
    session = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not session:
        conn.close()
        raise HTTPException(404, "Session not found")
    session = dict(session)
    start = session["started_at"]
    end   = session["ended_at"] or now_iso()

    rows = conn.execute("""
        SELECT item,
               SUM(qty)               AS total_qty,
               SUM(qty * price_value) AS total_value,
               COUNT(*)               AS drop_count,
               AVG(price_value)       AS avg_unit_price
        FROM drops
        WHERE SUBSTR(ts,1,19) >= ? AND SUBSTR(ts,1,19) <= ?
        GROUP BY item ORDER BY total_value DESC
    """, (start, end)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/sessions/{session_id}/timeline")
def session_timeline(session_id: int):
    conn = get_db()
    session = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not session:
        conn.close()
        raise HTTPException(404, "Session not found")
    session = dict(session)
    start = session["started_at"]
    end   = session["ended_at"] or now_iso()

    rows = conn.execute("""
        SELECT strftime('%Y-%m-%dT%H:%M', SUBSTR(ts,1,19)) AS bucket,
               item,
               SUM(qty * price_value) AS value
        FROM drops
        WHERE SUBSTR(ts,1,19) >= ? AND SUBSTR(ts,1,19) <= ?
        GROUP BY bucket, item
        ORDER BY bucket, item
    """, (start, end)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
