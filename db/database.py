"""
db/database.py — SQLite core for forex-agent

Three tables:
  manual_trades   — trades you log manually
  agent_signals   — ENTER_NOW signals from the scanner
  level_edits     — every SL/TP edit (old/new levels + reason) for model training

All writes go through this module. CSVs in logs/ are kept as-is (read-only backup).
Thread-safe: write lock for all INSERT/UPDATE, per-thread connections for reads.
"""

import os
import sqlite3
import threading
import logging

logger   = logging.getLogger(__name__)

_DB_PATH  = os.path.join(os.path.dirname(__file__), "..", "logs", "trades.db")
_write_lock = threading.Lock()

# Per-thread connection cache (reads)
_local = threading.local()


def _db_path() -> str:
    return os.path.abspath(_DB_PATH)


def _get_conn() -> sqlite3.Connection:
    """Return a per-thread SQLite connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(_db_path(), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")   # allows concurrent reads + writes
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


def init_db():
    """Create all tables if they don't exist. Call once at startup."""
    os.makedirs(os.path.dirname(_db_path()), exist_ok=True)
    conn = _get_conn()
    with _write_lock:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS manual_trades (
                signal_id       TEXT PRIMARY KEY,
                source          TEXT DEFAULT 'manual',
                timestamp_utc   TEXT,
                pair            TEXT,
                direction       TEXT,
                setup_type      TEXT,
                entry_price     REAL,
                sl_price        REAL,
                tp1_price       REAL,
                tp2_price       REAL,
                sl_pips         REAL,
                tp1_pips        REAL,
                tp2_pips        REAL,
                rr1             TEXT,
                outcome         TEXT DEFAULT '',
                outcome_pips    REAL,
                post_mortem     TEXT DEFAULT '',
                notes           TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS agent_signals (
                signal_id           TEXT PRIMARY KEY,
                timestamp_utc       TEXT,
                pair                TEXT,
                direction           TEXT,
                grade               TEXT,
                setup_type          TEXT,
                entry_price         REAL,
                sl_price            REAL,
                tp1_price           REAL,
                tp2_price           REAL,
                sl_pips             REAL,
                tp1_pips            REAL,
                tp2_pips            REAL,
                score               REAL,
                score_zone          REAL,
                score_tf            REAL,
                score_pattern       REAL,
                score_session       REAL,
                score_news          REAL,
                score_quality_bonus REAL,
                score_fvg           REAL,
                score_ict           REAL,
                h1_zone_type        TEXT,
                h1_zone_high        REAL,
                h1_zone_low         REAL,
                h1_zone_strength    REAL,
                h1_trend            TEXT,
                m15_trend           TEXT,
                m5_trend            TEXT,
                entry_pattern       TEXT,
                session             TEXT,
                killzone            TEXT,
                news_safe           INTEGER,
                alerted             INTEGER,
                taken               INTEGER DEFAULT 0,
                outcome             TEXT DEFAULT '',
                outcome_pips        REAL,
                notes               TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS level_edits (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id   TEXT,
                edited_at   TEXT,
                old_sl      REAL,
                new_sl      REAL,
                old_tp1     REAL,
                new_tp1     REAL,
                reason      TEXT DEFAULT '',
                FOREIGN KEY (signal_id) REFERENCES manual_trades(signal_id)
            );

            CREATE INDEX IF NOT EXISTS idx_manual_trades_pair      ON manual_trades(pair);
            CREATE INDEX IF NOT EXISTS idx_manual_trades_outcome    ON manual_trades(outcome);
            CREATE INDEX IF NOT EXISTS idx_agent_signals_pair       ON agent_signals(pair);
            CREATE INDEX IF NOT EXISTS idx_agent_signals_outcome    ON agent_signals(outcome);
            CREATE INDEX IF NOT EXISTS idx_level_edits_signal_id   ON level_edits(signal_id);
        """)
        conn.commit()
    # Migrations — add columns if they don't exist yet
    for col, typedef in [
        ("user_sl",   "REAL"),
        ("user_tp1",  "REAL"),
        ("actual_sl", "REAL"),
        ("actual_tp1","REAL"),
    ]:
        try:
            conn.execute(f"ALTER TABLE agent_signals ADD COLUMN {col} {typedef}")
            conn.commit()
        except Exception:
            pass  # column already exists

    logger.info(f"SQLite DB ready at {_db_path()}")


# ── MANUAL TRADES ─────────────────────────────────────────────────────────────

def insert_manual_trade(row: dict):
    conn = _get_conn()
    with _write_lock:
        conn.execute("""
            INSERT OR IGNORE INTO manual_trades
            (signal_id, source, timestamp_utc, pair, direction, setup_type,
             entry_price, sl_price, tp1_price, tp2_price,
             sl_pips, tp1_pips, tp2_pips, rr1, outcome, outcome_pips,
             post_mortem, notes)
            VALUES
            (:signal_id, :source, :timestamp_utc, :pair, :direction, :setup_type,
             :entry_price, :sl_price, :tp1_price, :tp2_price,
             :sl_pips, :tp1_pips, :tp2_pips, :rr1, :outcome, :outcome_pips,
             :post_mortem, :notes)
        """, row)
        conn.commit()


def update_manual_trade_outcome(signal_id: str, outcome: str, outcome_pips: float, post_mortem: str):
    conn = _get_conn()
    with _write_lock:
        conn.execute("""
            UPDATE manual_trades
            SET outcome=?, outcome_pips=?, post_mortem=?
            WHERE signal_id=?
        """, (outcome, outcome_pips, post_mortem, signal_id))
        conn.commit()


def update_manual_trade_levels(signal_id: str, sl_price: float, tp1_price: float,
                                sl_pips: float, tp1_pips: float, rr1: str):
    conn = _get_conn()
    with _write_lock:
        conn.execute("""
            UPDATE manual_trades
            SET sl_price=?, tp1_price=?, sl_pips=?, tp1_pips=?, rr1=?
            WHERE signal_id=?
        """, (sl_price, tp1_price, sl_pips, tp1_pips, rr1, signal_id))
        conn.commit()


def get_manual_trade(signal_id: str) -> dict | None:
    conn = _get_conn()
    row  = conn.execute(
        "SELECT * FROM manual_trades WHERE signal_id=?", (signal_id,)
    ).fetchone()
    return dict(row) if row else None


def get_open_manual_trades() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM manual_trades WHERE outcome IS NULL OR outcome = '' ORDER BY timestamp_utc DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_recent_manual_trades(limit: int = 100) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM manual_trades ORDER BY timestamp_utc DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


# ── LEVEL EDITS ───────────────────────────────────────────────────────────────

def insert_level_edit(signal_id: str, old_sl: float, new_sl: float,
                      old_tp1: float, new_tp1: float, reason: str = ""):
    from datetime import datetime, timezone
    conn = _get_conn()
    with _write_lock:
        conn.execute("""
            INSERT INTO level_edits (signal_id, edited_at, old_sl, new_sl, old_tp1, new_tp1, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (signal_id, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
              old_sl, new_sl, old_tp1, new_tp1, reason))
        conn.commit()


def get_level_edits(signal_id: str) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM level_edits WHERE signal_id=? ORDER BY edited_at", (signal_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# ── AGENT SIGNALS ─────────────────────────────────────────────────────────────

def insert_agent_signal(row: dict):
    conn = _get_conn()
    with _write_lock:
        conn.execute("""
            INSERT OR IGNORE INTO agent_signals
            (signal_id, timestamp_utc, pair, direction, grade, setup_type,
             entry_price, sl_price, tp1_price, tp2_price,
             sl_pips, tp1_pips, tp2_pips, score,
             score_zone, score_tf, score_pattern, score_session, score_news,
             score_quality_bonus, score_fvg, score_ict,
             h1_zone_type, h1_zone_high, h1_zone_low, h1_zone_strength,
             h1_trend, m15_trend, m5_trend,
             entry_pattern, session, killzone, news_safe, alerted,
             taken, outcome, outcome_pips, notes)
            VALUES
            (:signal_id, :timestamp_utc, :pair, :direction, :grade, :setup_type,
             :entry_price, :sl_price, :tp1_price, :tp2_price,
             :sl_pips, :tp1_pips, :tp2_pips, :score,
             :score_zone, :score_tf, :score_pattern, :score_session, :score_news,
             :score_quality_bonus, :score_fvg, :score_ict,
             :h1_zone_type, :h1_zone_high, :h1_zone_low, :h1_zone_strength,
             :h1_trend, :m15_trend, :m5_trend,
             :entry_pattern, :session, :killzone, :news_safe, :alerted,
             :taken, :outcome, :outcome_pips, :notes)
        """, row)
        conn.commit()


def update_agent_signal_taken(signal_id: str):
    conn = _get_conn()
    with _write_lock:
        conn.execute("UPDATE agent_signals SET taken=1 WHERE signal_id=?", (signal_id,))
        conn.commit()


def update_agent_signal_took_it(signal_id: str, user_sl: float | None, user_tp1: float | None):
    """
    Mark signal as taken + save user's actual SL/TP.
    actual_sl/tp1 = user's levels if provided, else falls back to scanner levels.
    """
    conn = _get_conn()
    # Fetch scanner levels as fallback
    row = conn.execute(
        "SELECT sl_price, tp1_price FROM agent_signals WHERE signal_id=?", (signal_id,)
    ).fetchone()
    scanner_sl  = row["sl_price"]  if row else None
    scanner_tp1 = row["tp1_price"] if row else None

    actual_sl  = user_sl  if user_sl  is not None else scanner_sl
    actual_tp1 = user_tp1 if user_tp1 is not None else scanner_tp1

    with _write_lock:
        conn.execute("""
            UPDATE agent_signals
            SET taken=1, user_sl=?, user_tp1=?, actual_sl=?, actual_tp1=?
            WHERE signal_id=?
        """, (user_sl, user_tp1, actual_sl, actual_tp1, signal_id))
        conn.commit()


def update_agent_signal_outcome(signal_id: str, outcome: str, pips: float, notes: str = ""):
    conn = _get_conn()
    with _write_lock:
        conn.execute("""
            UPDATE agent_signals SET outcome=?, outcome_pips=?, notes=?
            WHERE signal_id=?
        """, (outcome, pips, notes, signal_id))
        conn.commit()


def get_recent_agent_signals(limit: int = 20) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM agent_signals ORDER BY timestamp_utc DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_agent_signal(signal_id: str) -> dict | None:
    conn = _get_conn()
    row  = conn.execute(
        "SELECT * FROM agent_signals WHERE signal_id=?", (signal_id,)
    ).fetchone()
    return dict(row) if row else None


# ── PERFORMANCE SUMMARY ───────────────────────────────────────────────────────

def get_performance_summary_db() -> dict:
    conn = _get_conn()

    # Agent signals stats
    agent_rows = conn.execute(
        "SELECT outcome, outcome_pips, grade, taken FROM agent_signals WHERE outcome != ''"
    ).fetchall()

    # Manual trades stats
    manual_rows = conn.execute(
        "SELECT outcome, outcome_pips FROM manual_trades WHERE outcome != ''"
    ).fetchall()

    def _stats(rows):
        wins   = sum(1 for r in rows if r["outcome"] == "WIN")
        losses = sum(1 for r in rows if r["outcome"] == "LOSS")
        total  = wins + losses
        pips   = [float(r["outcome_pips"]) for r in rows if r["outcome_pips"] is not None]
        return {
            "wins":     wins,
            "losses":   losses,
            "total":    total,
            "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
            "avg_pips": round(sum(pips) / len(pips), 1) if pips else 0,
        }

    agent_stats  = _stats(agent_rows)
    manual_stats = _stats(manual_rows)

    # Grade breakdown (agent signals)
    by_grade = {}
    for grade in ["A+", "A", "B", "C"]:
        g_rows = [r for r in agent_rows if r["grade"] == grade]
        if g_rows:
            gw = sum(1 for r in g_rows if r["outcome"] == "WIN")
            by_grade[grade] = {
                "count":    len(g_rows),
                "wins":     gw,
                "win_rate": round(gw / len(g_rows) * 100, 1),
            }

    taken_count = sum(1 for r in agent_rows if r["taken"])

    total_signals = conn.execute("SELECT COUNT(*) FROM agent_signals").fetchone()[0]

    return {
        "total_signals": total_signals,
        "agent":         agent_stats,
        "manual":        manual_stats,
        "taken_count":   taken_count,
        "by_grade":      by_grade,
        # legacy keys for dashboard compat
        "completed":     agent_stats["total"],
        "wins":          agent_stats["wins"],
        "losses":        agent_stats["losses"],
        "win_rate":      agent_stats["win_rate"],
        "avg_pips":      agent_stats["avg_pips"],
    }
