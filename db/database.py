"""
db/database.py — SQLite core for forex-agent

Four tables:
  manual_trades   — trades you log manually
  agent_signals   — ENTER_NOW signals from the scanner
  level_edits     — every SL/TP edit (old/new levels + reason) for model training
  journal_entries — session diary: patterns, mistakes, observations, rules

All writes go through this module. CSVs in logs/ are kept as-is (read-only backup).
Thread-safe: write lock for all INSERT/UPDATE, per-thread connections for reads.
"""

import os
import sqlite3
import threading
import logging

logger      = logging.getLogger(__name__)
_write_lock = threading.Lock()
_local      = threading.local()

# Railway Volume at /data, local fallback to logs/trades.db
if os.path.isdir("/data"):
    _DB_PATH = "/data/forex.db"
else:
    _DB_PATH = os.path.join(os.path.dirname(__file__), "..", "logs", "trades.db")


def _db_path() -> str:
    return os.path.abspath(_DB_PATH)


def _get_conn() -> sqlite3.Connection:
    """Return a per-thread SQLite connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(_db_path(), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout = 5000")   # wait 5s on lock, don't crash
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

            CREATE TABLE IF NOT EXISTS journal_entries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date  TEXT,
                session     TEXT DEFAULT 'any',
                tags        TEXT DEFAULT '',
                content     TEXT,
                created_at  TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_journal_date    ON journal_entries(entry_date);
            CREATE INDEX IF NOT EXISTS idx_journal_session ON journal_entries(session);

            CREATE TABLE IF NOT EXISTS sync_status (
                id             INTEGER PRIMARY KEY DEFAULT 1,
                agent_signals  INTEGER DEFAULT 0,
                manual_trades  INTEGER DEFAULT 0,
                synced_at      TEXT
            );
        """)
        conn.commit()
    # ── MIGRATIONS ────────────────────────────────────────────────────────────
    # agent_signals: extra user/actual level columns + oanda_trade_id
    for col, typedef in [
        ("user_sl",              "REAL"),
        ("user_tp1",             "REAL"),
        ("actual_sl",            "REAL"),
        ("actual_tp1",           "REAL"),
        ("oanda_trade_id",       "TEXT"),    # OANDA fill trade ID — needed to update GTC orders
        ("exit_price",           "REAL"),    # actual close price if closed early/mid-trade
        ("h1_trend_at_entry",    "TEXT"),    # H1 candle direction at signal time (for training)
        ("is_archived",          "INTEGER DEFAULT 0"),  # soft-delete: hidden from dashboard, kept for training
        ("signal_mode",          "TEXT"),    # "normal" or "news_sniper" — mode when signal fired
        # ── Session/weekend guard audit fields (added: production guard patch) ──
        ("weekend_block",        "INTEGER DEFAULT 0"),  # 1 = Saturday or Sunday-pre-open caused block
        ("session_block",        "INTEGER DEFAULT 0"),  # 1 = Friday pre-close caused block
        ("market_closed",        "INTEGER DEFAULT 0"),  # 1 = market fully closed at signal time
        ("low_liquidity_window", "INTEGER DEFAULT 0"),  # 1 = caution window (not a hard block)
        ("blocked_reason",       "TEXT DEFAULT ''"),    # machine-readable slug, e.g. SATURDAY_MARKET_CLOSED
        ("entry_allowed",        "INTEGER DEFAULT 1"),  # 0 when guard blocked ENTER_NOW
        # ── Manual exclusion audit fields (added: bad-run window patch) ────────
        ("archive_reason",       "TEXT DEFAULT ''"),    # free-text label for why this was archived
        ("manual_exclusion",     "INTEGER DEFAULT 0"),  # 1 = excluded by explicit operator decision
    ]:
        try:
            conn.execute(f"ALTER TABLE agent_signals ADD COLUMN {col} {typedef}")
            conn.commit()
        except Exception:
            pass  # column already exists

    # manual_trades: model-training context fields
    for col, typedef in [
        ("session",     "TEXT"),
        ("killzone",    "TEXT"),
        ("h1_trend",    "TEXT"),
        ("m15_trend",   "TEXT"),
        ("m5_trend",    "TEXT"),
        ("news_safe",   "INTEGER"),
        ("is_archived", "INTEGER DEFAULT 0"),  # soft-delete for manual trades
        ("signal_mode", "TEXT"),               # "normal" or "news_sniper"
    ]:
        try:
            conn.execute(f"ALTER TABLE manual_trades ADD COLUMN {col} {typedef}")
            conn.commit()
        except Exception:
            pass  # column already exists

    # level_edits: remove FOREIGN KEY constraint (blocks agent signal edits),
    # add source column (manual/agent) so we know which table each edit belongs to.
    # Migration is idempotent — only runs if source column is missing.
    le_cols = [r[1] for r in conn.execute("PRAGMA table_info(level_edits)").fetchall()]
    if "source" not in le_cols:
        try:
            with _write_lock:
                conn.executescript("""
                    CREATE TABLE level_edits_new (
                        id            INTEGER PRIMARY KEY AUTOINCREMENT,
                        signal_id     TEXT,
                        source        TEXT DEFAULT 'manual',
                        edited_at     TEXT,
                        old_sl        REAL,
                        new_sl        REAL,
                        old_tp1       REAL,
                        new_tp1       REAL,
                        reason        TEXT DEFAULT '',
                        oanda_synced  INTEGER DEFAULT 0
                    );
                    INSERT INTO level_edits_new
                        (id, signal_id, source, edited_at, old_sl, new_sl, old_tp1, new_tp1, reason, oanda_synced)
                    SELECT id, signal_id, 'manual', edited_at, old_sl, new_sl, old_tp1, new_tp1, reason, 0
                    FROM level_edits;
                    DROP TABLE level_edits;
                    ALTER TABLE level_edits_new RENAME TO level_edits;
                    CREATE INDEX IF NOT EXISTS idx_level_edits_signal_id ON level_edits(signal_id);
                    CREATE INDEX IF NOT EXISTS idx_level_edits_source    ON level_edits(source);
                """)
            logger.info("level_edits migrated: FK removed, source + oanda_synced columns added")
        except Exception as e:
            logger.warning(f"level_edits migration failed (may already be done): {e}")

    # Backfill: signal_mode NULL → 'normal' for all pre-existing rows
    try:
        r1 = conn.execute("UPDATE agent_signals SET signal_mode='normal' WHERE signal_mode IS NULL")
        r2 = conn.execute("UPDATE manual_trades  SET signal_mode='normal' WHERE signal_mode IS NULL")
        conn.commit()
        if r1.rowcount or r2.rowcount:
            logger.info(f"Backfilled signal_mode: agent_signals={r1.rowcount} manual_trades={r2.rowcount}")
    except Exception as e:
        logger.warning(f"signal_mode backfill failed (non-fatal): {e}")

    logger.info(f"SQLite DB ready at {_db_path()}")
    # Archive signals from closed-market windows (idempotent, runs every startup).
    try:
        archive_bad_window_signals()
    except Exception as e:
        logger.warning(f"archive_bad_window_signals failed at startup (non-fatal): {e}")
    # Archive signals from the approved bad-run window (May 15–18 2026).
    try:
        archive_bad_run_window()
    except Exception as e:
        logger.warning(f"archive_bad_run_window failed at startup (non-fatal): {e}")


# ── MANUAL TRADES ─────────────────────────────────────────────────────────────

def insert_manual_trade(row: dict):
    conn = _get_conn()
    with _write_lock:
        conn.execute("""
            INSERT OR IGNORE INTO manual_trades
            (signal_id, source, timestamp_utc, pair, direction, setup_type,
             entry_price, sl_price, tp1_price, tp2_price,
             sl_pips, tp1_pips, tp2_pips, rr1, outcome, outcome_pips,
             post_mortem, notes, session, killzone, h1_trend, m15_trend, m5_trend,
             news_safe, signal_mode)
            VALUES
            (:signal_id, :source, :timestamp_utc, :pair, :direction, :setup_type,
             :entry_price, :sl_price, :tp1_price, :tp2_price,
             :sl_pips, :tp1_pips, :tp2_pips, :rr1, :outcome, :outcome_pips,
             :post_mortem, :notes,
             :session, :killzone, :h1_trend, :m15_trend, :m5_trend,
             :news_safe, :signal_mode)
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
                      old_tp1: float, new_tp1: float, reason: str = "",
                      source: str = "manual", oanda_synced: int = 0):
    """
    Log a SL/TP level change.
    source: 'manual' (manual_trades) or 'agent' (agent_signals)
    oanda_synced: 1 if the change was also pushed to the live OANDA GTC order
    """
    from datetime import datetime, timezone
    conn = _get_conn()
    with _write_lock:
        conn.execute("""
            INSERT INTO level_edits
                (signal_id, source, edited_at, old_sl, new_sl, old_tp1, new_tp1, reason, oanda_synced)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (signal_id, source,
              datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
              old_sl, new_sl, old_tp1, new_tp1, reason, oanda_synced))
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
             taken, outcome, outcome_pips, notes, signal_mode)
            VALUES
            (:signal_id, :timestamp_utc, :pair, :direction, :grade, :setup_type,
             :entry_price, :sl_price, :tp1_price, :tp2_price,
             :sl_pips, :tp1_pips, :tp2_pips, :score,
             :score_zone, :score_tf, :score_pattern, :score_session, :score_news,
             :score_quality_bonus, :score_fvg, :score_ict,
             :h1_zone_type, :h1_zone_high, :h1_zone_low, :h1_zone_strength,
             :h1_trend, :m15_trend, :m5_trend,
             :entry_pattern, :session, :killzone, :news_safe, :alerted,
             :taken, :outcome, :outcome_pips, :notes, :signal_mode)
        """, row)
        conn.commit()


def update_agent_signal_taken(signal_id: str):
    conn = _get_conn()
    with _write_lock:
        conn.execute("UPDATE agent_signals SET taken=1 WHERE signal_id=?", (signal_id,))
        conn.commit()


def update_agent_signal_took_it(signal_id: str, user_sl: float | None, user_tp1: float | None,
                                oanda_trade_id: str | None = None):
    """
    Mark signal as taken + save user's actual SL/TP + OANDA trade ID.
    actual_sl/tp1 = user's levels if provided, else falls back to scanner levels.
    oanda_trade_id: fill trade ID from OANDA — stored so we can update GTC orders later.
    """
    conn = _get_conn()
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
            SET taken=1, user_sl=?, user_tp1=?, actual_sl=?, actual_tp1=?, oanda_trade_id=?
            WHERE signal_id=?
        """, (user_sl, user_tp1, actual_sl, actual_tp1, oanda_trade_id, signal_id))
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
        "SELECT * FROM agent_signals WHERE COALESCE(is_archived,0)=0 ORDER BY timestamp_utc DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def archive_bad_window_signals() -> int:
    """
    One-time cleanup: soft-archive agent_signals that were logged during
    closed-market windows (Saturday all-day, Sunday before 22:00 UTC,
    Friday 21:30+ UTC).

    These signals polluted win-rate stats. They are NOT deleted — is_archived=1
    keeps them out of dashboards and performance queries while preserving the
    raw data for training analysis.

    Returns the count of rows archived. Safe to call multiple times (idempotent).
    """
    conn = _get_conn()
    # Build a SQLite expression that detects bad-window timestamps.
    # strftime('%w', ...) returns day-of-week: 0=Sunday, 6=Saturday in SQLite.
    # Times are stored as "YYYY-MM-DD HH:MM:SS" UTC strings.
    with _write_lock:
        result = conn.execute("""
            UPDATE agent_signals
            SET    is_archived   = 1,
                   market_closed = 1,
                   blocked_reason = CASE
                       WHEN strftime('%w', timestamp_utc) = '6'
                            THEN 'SATURDAY_MARKET_CLOSED'
                       WHEN strftime('%w', timestamp_utc) = '0'
                            AND CAST(strftime('%H', timestamp_utc) AS INTEGER) < 22
                            THEN 'SUNDAY_MARKET_CLOSED'
                       WHEN strftime('%w', timestamp_utc) = '5'
                            AND (
                                CAST(strftime('%H', timestamp_utc) AS INTEGER) > 21
                                OR (
                                    CAST(strftime('%H', timestamp_utc) AS INTEGER) = 21
                                    AND CAST(strftime('%M', timestamp_utc) AS INTEGER) >= 30
                                )
                            )
                            THEN 'FRIDAY_PRE_CLOSE'
                       ELSE blocked_reason
                   END,
                   weekend_block = CASE
                       WHEN strftime('%w', timestamp_utc) IN ('0', '6') THEN 1
                       ELSE weekend_block
                   END,
                   session_block = CASE
                       WHEN strftime('%w', timestamp_utc) = '5'
                            AND (
                                CAST(strftime('%H', timestamp_utc) AS INTEGER) > 21
                                OR (
                                    CAST(strftime('%H', timestamp_utc) AS INTEGER) = 21
                                    AND CAST(strftime('%M', timestamp_utc) AS INTEGER) >= 30
                                )
                            ) THEN 1
                       ELSE session_block
                   END
            WHERE  COALESCE(is_archived, 0) = 0
              AND (
                -- Saturday all day (SQLite: %w=6)
                strftime('%w', timestamp_utc) = '6'
                OR
                -- Sunday before 22:00 UTC (SQLite: %w=0)
                (
                    strftime('%w', timestamp_utc) = '0'
                    AND CAST(strftime('%H', timestamp_utc) AS INTEGER) < 22
                )
                OR
                -- Friday 21:30 UTC onwards (SQLite: %w=5)
                (
                    strftime('%w', timestamp_utc) = '5'
                    AND (
                        CAST(strftime('%H', timestamp_utc) AS INTEGER) > 21
                        OR (
                            CAST(strftime('%H', timestamp_utc) AS INTEGER) = 21
                            AND CAST(strftime('%M', timestamp_utc) AS INTEGER) >= 30
                        )
                    )
                )
              )
        """)
        conn.commit()
    count = result.rowcount
    if count:
        logger.info(
            f"archive_bad_window_signals: archived {count} bad-window signals "
            f"(Saturday/Sunday-pre-open/Friday-pre-close). "
            f"Rows kept in DB with is_archived=1."
        )
    return count


# Bad-run window constants — scanner over-signaling period May 15–18 2026.
# Approved by Om for manual exclusion. Keep as constants so tests can import them.
BAD_RUN_WINDOW_START = "2026-05-15 00:00:00"
BAD_RUN_WINDOW_END   = "2026-05-18 01:07:52"


def archive_bad_run_window(
    start_utc: str = BAD_RUN_WINDOW_START,
    end_utc:   str = BAD_RUN_WINDOW_END,
) -> int:
    """
    Soft-archive agent_signals logged during the known scanner over-signaling
    period (May 15–18 2026) when debug instability caused spurious signals.

    These signals were generated during valid market hours but are NOT reliable
    production data. Om approved manual exclusion on 2026-05-18.

    Marks rows:
      is_archived      = 1
      manual_exclusion = 1
      blocked_reason   = "bad_run_bug_window"
      archive_reason   = "scanner_over_signaling_may15_may18"

    Idempotent — safe to run on every startup. Returns count of rows archived.
    Does NOT delete any rows.
    """
    conn = _get_conn()
    with _write_lock:
        result = conn.execute("""
            UPDATE agent_signals
            SET is_archived      = 1,
                manual_exclusion = 1,
                blocked_reason   = 'bad_run_bug_window',
                archive_reason   = 'scanner_over_signaling_may15_may18'
            WHERE COALESCE(is_archived, 0) = 0
              AND timestamp_utc >= ?
              AND timestamp_utc <= ?
        """, (start_utc, end_utc))
        conn.commit()
    count = result.rowcount
    if count:
        logger.info(
            f"archive_bad_run_window: archived {count} signals from {start_utc} → {end_utc} "
            f"(scanner_over_signaling_may15_may18). "
            f"Rows kept in DB with is_archived=1, manual_exclusion=1."
        )
    return count


def get_unlabeled_taken_signals() -> list[dict]:
    """
    All signals with no outcome, no early exit, and SL/TP resolvable.
    Taken or not — if SL/TP is set, price will hit one eventually.
    Uses user_sl/tp1 when available, falls back to actual_sl/tp1, then sl_price/tp1_price.
    """
    conn = _get_conn()
    rows = conn.execute("""
        SELECT signal_id, pair, direction, timestamp_utc, entry_price,
               user_sl, user_tp1, actual_sl, actual_tp1, sl_price, tp1_price, exit_price
        FROM agent_signals
        WHERE COALESCE(is_archived,0)=0
          AND (outcome IS NULL OR outcome = '')
          AND (exit_price IS NULL OR exit_price = 0)
          AND COALESCE(user_sl,   actual_sl,   sl_price)  > 0
          AND COALESCE(user_tp1,  actual_tp1,  tp1_price) > 0
        ORDER BY timestamp_utc ASC
    """).fetchall()
    return [dict(r) for r in rows]


def close_agent_trade(signal_id: str, exit_price: float, entry_price: float,
                      direction: str, pip: float) -> dict:
    """
    Close an agent signal mid-trade at exit_price.
    Calculates outcome + pips direction-aware, writes to DB.
    Returns {outcome, outcome_pips}.
    """
    is_bull = "bull" in direction.lower()
    if is_bull:
        pips = round((exit_price - entry_price) / pip, 1)
    else:
        pips = round((entry_price - exit_price) / pip, 1)

    outcome = "WIN" if pips > 0 else "LOSS"
    note = f"[early close] {outcome} {pips:+.1f}p @ {exit_price}"

    conn = _get_conn()
    with _write_lock:
        conn.execute("""
            UPDATE agent_signals
            SET exit_price=?, outcome=?, outcome_pips=?, notes=?
            WHERE signal_id=?
        """, (exit_price, outcome, pips, note, signal_id))
        conn.commit()

    return {"outcome": outcome, "outcome_pips": pips}


def get_agent_signal(signal_id: str) -> dict | None:
    conn = _get_conn()
    row  = conn.execute(
        "SELECT * FROM agent_signals WHERE signal_id=?", (signal_id,)
    ).fetchone()
    return dict(row) if row else None


# ── PERFORMANCE SUMMARY ───────────────────────────────────────────────────────

def save_note(signal_id: str, note: str, kind: str = "manual"):
    """Append a note to manual_trades or agent_signals. kind: 'manual' | 'agent'"""
    conn  = _get_conn()
    table = "manual_trades" if kind == "manual" else "agent_signals"
    row   = conn.execute(f"SELECT notes FROM {table} WHERE signal_id=?", (signal_id,)).fetchone()
    if row is None:
        return False
    existing = row["notes"] or ""
    from datetime import datetime, timezone
    ts  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    new = f"{existing}\n[{ts}] {note}".strip()
    with _write_lock:
        conn.execute(f"UPDATE {table} SET notes=? WHERE signal_id=?", (new, signal_id))
        conn.commit()
    return True


def update_agent_signal_levels(signal_id: str, user_sl: float | None, user_tp1: float | None):
    """Update user SL/TP on an agent signal (without changing taken status)."""
    conn = _get_conn()
    row  = conn.execute(
        "SELECT sl_price, tp1_price FROM agent_signals WHERE signal_id=?", (signal_id,)
    ).fetchone()
    if not row:
        return False
    actual_sl  = user_sl  if user_sl  is not None else row["sl_price"]
    actual_tp1 = user_tp1 if user_tp1 is not None else row["tp1_price"]
    with _write_lock:
        conn.execute("""
            UPDATE agent_signals SET user_sl=?, user_tp1=?, actual_sl=?, actual_tp1=?
            WHERE signal_id=?
        """, (user_sl, user_tp1, actual_sl, actual_tp1, signal_id))
        conn.commit()
    return True


def get_performance_summary_db(bad_run_window: tuple | None = None) -> dict:
    """
    Performance summary from SQLite.

    Archived signals (is_archived=1) are always excluded — they were logged
    during closed-market windows and must not pollute win-rate stats.

    bad_run_window: optional (start_utc_str, end_utc_str) tuple to exclude an
    additional manual date range. Pass None (default) to leave it off.
    Example: ("2026-05-15 00:00:00", "2026-05-18 01:07:52")

    Returns audit fields:
      stats_source            "sqlite"
      excluded_archived_count rows excluded by is_archived=1
      excluded_bad_window_count rows excluded by bad_run_window (0 if not applied)
      bad_run_window_applied  bool
    """
    conn = _get_conn()

    # Count archived rows (excluded regardless of bad_run_window)
    excluded_archived = conn.execute(
        "SELECT COUNT(*) FROM agent_signals WHERE COALESCE(is_archived,0)=1"
    ).fetchone()[0]

    # Build optional bad-run window clause
    bad_window_clause       = ""
    excluded_bad_window_cnt = 0
    bad_run_applied         = False
    if bad_run_window:
        start_str, end_str   = bad_run_window
        bad_window_clause    = f" AND (timestamp_utc < '{start_str}' OR timestamp_utc > '{end_str}')"
        excluded_bad_window_cnt = conn.execute(
            """SELECT COUNT(*) FROM agent_signals
               WHERE COALESCE(is_archived,0)=0
                 AND timestamp_utc >= ? AND timestamp_utc <= ?""",
            (start_str, end_str)
        ).fetchone()[0]
        bad_run_applied = True

    base_where = f"COALESCE(is_archived,0)=0{bad_window_clause}"

    # Agent signals stats
    agent_rows = conn.execute(
        f"SELECT outcome, outcome_pips, grade, taken FROM agent_signals "
        f"WHERE {base_where} AND outcome != ''"
    ).fetchall()

    # Manual trades stats (no bad-window concept — manual trades are always valid)
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

    # taken_count = all signals ever taken (not just labeled ones)
    taken_count   = conn.execute(
        f"SELECT COUNT(*) FROM agent_signals WHERE {base_where} AND taken = 1"
    ).fetchone()[0]
    total_signals = conn.execute(
        f"SELECT COUNT(*) FROM agent_signals WHERE {base_where}"
    ).fetchone()[0]
    total_manual  = conn.execute("SELECT COUNT(*) FROM manual_trades").fetchone()[0]

    combined_total = agent_stats["total"] + manual_stats["total"]
    combined_wins  = agent_stats["wins"]  + manual_stats["wins"]
    combined_loss  = agent_stats["losses"] + manual_stats["losses"]

    return {
        # ── audit ──────────────────────────────────────────────────────────
        "stats_source":               "sqlite",
        "excluded_archived_count":    excluded_archived,
        "excluded_bad_window_count":  excluded_bad_window_cnt,
        "bad_run_window_applied":     bad_run_applied,
        # ── counts ─────────────────────────────────────────────────────────
        "total_signals": total_signals,
        "total_manual":  total_manual,
        "agent":         agent_stats,
        "manual":        manual_stats,
        "taken_count":   taken_count,
        "by_grade":      by_grade,
        # ── legacy keys for dashboard compat ───────────────────────────────
        "completed": combined_total,
        "wins":      combined_wins,
        "losses":    combined_loss,
        "win_rate":  round(combined_wins / combined_total * 100, 1) if combined_total > 0 else 0,
        "avg_pips":  agent_stats["avg_pips"],
    }


# ── LEVEL EDITS — EXPORT / IMPORT ────────────────────────────────────────────

def get_all_level_edits(limit: int = 100_000) -> list[dict]:
    """Return all level_edits rows for export/sync."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM level_edits ORDER BY edited_at ASC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def insert_level_edit_row(row: dict):
    """
    Upsert a level_edit row from export data (sync/import).
    Uses INSERT OR REPLACE to handle both new and updated rows.
    """
    conn = _get_conn()
    cols = ["id","signal_id","source","edited_at","old_sl","new_sl","old_tp1","new_tp1","reason","oanda_synced"]
    with _write_lock:
        conn.execute(
            f"INSERT OR REPLACE INTO level_edits ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
            [row.get(c) for c in cols]
        )
        conn.commit()


# ── JOURNAL ENTRIES ───────────────────────────────────────────────────────────

def add_journal_entry(entry_date: str, session: str, tags: str, content: str) -> int:
    """
    Insert a journal entry. Returns the new row id.
    entry_date: YYYY-MM-DD
    session:    tokyo | london | new_york | any
    tags:       comma-separated — pattern,mistake,observation,rule
    content:    free text
    """
    from datetime import datetime, timezone
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn = _get_conn()
    with _write_lock:
        cur = conn.execute(
            "INSERT INTO journal_entries (entry_date, session, tags, content, created_at) VALUES (?,?,?,?,?)",
            (entry_date, session, tags, content, created_at)
        )
        conn.commit()
        return cur.lastrowid


def get_journal_entries(limit: int = 200, tag: str = "", session: str = "") -> list[dict]:
    """
    Fetch journal entries, newest first.
    Optional tag filter (substring match on tags column).
    Optional session filter (exact match).
    """
    conn  = _get_conn()
    query = "SELECT * FROM journal_entries"
    args  = []
    conds = []
    if tag:
        conds.append("tags LIKE ?")
        args.append(f"%{tag}%")
    if session and session != "any":
        conds.append("session = ?")
        args.append(session)
    if conds:
        query += " WHERE " + " AND ".join(conds)
    query += " ORDER BY entry_date DESC, created_at DESC LIMIT ?"
    args.append(limit)
    rows = conn.execute(query, args).fetchall()
    return [dict(r) for r in rows]


def delete_journal_entry(entry_id: int) -> bool:
    """Delete a journal entry by id. Returns True if a row was deleted."""
    conn = _get_conn()
    with _write_lock:
        cur = conn.execute("DELETE FROM journal_entries WHERE id=?", (entry_id,))
        conn.commit()
        return cur.rowcount > 0


def get_all_journal_entries(limit: int = 100_000) -> list[dict]:
    """Return all journal_entries rows for export/sync."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM journal_entries ORDER BY created_at ASC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def insert_journal_entry_row(row: dict) -> None:
    """
    Upsert a journal_entry row from export data (sync/import).
    Uses INSERT OR REPLACE to handle both new and updated rows.
    """
    conn = _get_conn()
    cols = ["id","entry_date","session","tags","content","created_at"]
    with _write_lock:
        conn.execute(
            f"INSERT OR REPLACE INTO journal_entries ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
            [row.get(c) for c in cols]
        )
        conn.commit()


def get_sync_status() -> dict:
    """Return last known local sync counts posted by sync.py."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM sync_status WHERE id = 1").fetchone()
    if not row:
        return {"agent_signals": None, "manual_trades": None, "synced_at": None}
    return dict(row)


def set_sync_status(agent_signals: int, manual_trades: int, synced_at: str) -> None:
    """Called by sync.py after every successful sync — stores local counts on Railway."""
    conn = _get_conn()
    with _write_lock:
        conn.execute("""
            INSERT INTO sync_status (id, agent_signals, manual_trades, synced_at)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                agent_signals = excluded.agent_signals,
                manual_trades = excluded.manual_trades,
                synced_at     = excluded.synced_at
        """, (agent_signals, manual_trades, synced_at))
        conn.commit()
