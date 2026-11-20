"""
Database schema and storage management using SQLite and SQLAlchemy.
Implements audit logs, user strategies, signals, active trades,
trade journals, and prop firm profiles.
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from backend.config import DATABASE_PATH

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=30000;")
    except Exception:
        pass

    # 0. Users Table (Authentication & Privacy)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_confirmed INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)

    # Upgrade users schema if is_confirmed column does not exist
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN is_confirmed INTEGER DEFAULT 0;")
    except sqlite3.OperationalError:
        pass

    # 0b. Authentication OTPs Table (Email Confirmation & 2FA Login)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS auth_otps (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        email TEXT NOT NULL,
        otp_code TEXT NOT NULL,
        purpose TEXT NOT NULL,
        session_token TEXT,
        expires_at TEXT NOT NULL,
        used INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)

    # 0c. User Broker Accounts (Partitioned Per-User Isolation)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_broker_configs (
        user_id TEXT PRIMARY KEY,
        broker TEXT NOT NULL DEFAULT 'paper',
        credentials TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # 1. Strategies Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS strategies (
        id TEXT PRIMARY KEY,
        user_id TEXT DEFAULT 'SYSTEM',
        name TEXT NOT NULL,
        description TEXT,
        strategy_type TEXT NOT NULL,
        instruments TEXT NOT NULL,       -- JSON array of symbols
        timeframes TEXT NOT NULL,        -- JSON array of timeframes
        sessions TEXT NOT NULL,          -- JSON array of allowed sessions
        rules TEXT NOT NULL,             -- JSON rule tree with AND/OR logic
        risk_settings TEXT NOT NULL,     -- JSON risk parameters
        is_active INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Upgrade schema if user_id column doesn't exist yet
    try:
        cursor.execute("ALTER TABLE strategies ADD COLUMN user_id TEXT DEFAULT 'SYSTEM';")
    except sqlite3.OperationalError:
        pass

    # 2. Signals Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS signals (
        id TEXT PRIMARY KEY,
        strategy_id TEXT,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        direction TEXT NOT NULL,         -- BUY or SELL
        entry_price REAL NOT NULL,
        stop_loss REAL NOT NULL,
        take_profit REAL NOT NULL,
        risk_reward_ratio REAL NOT NULL,
        position_size_lots REAL NOT NULL,
        confidence_score REAL NOT NULL,
        market_structure_summary TEXT,
        conditions_satisfied TEXT,       -- JSON list
        conditions_not_satisfied TEXT,   -- JSON list
        status TEXT NOT NULL,            -- PENDING, APPROVED, REJECTED, EXECUTED, EXPIRED
        created_at TEXT NOT NULL,
        executed_at TEXT
    );
    """)

    # 3. Orders & Positions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS positions (
        ticket TEXT PRIMARY KEY,
        signal_id TEXT,
        strategy_id TEXT,
        broker TEXT NOT NULL,
        symbol TEXT NOT NULL,
        direction TEXT NOT NULL,
        volume REAL NOT NULL,
        entry_price REAL NOT NULL,
        current_price REAL NOT NULL,
        stop_loss REAL NOT NULL,
        take_profit REAL NOT NULL,
        pnl REAL DEFAULT 0.0,
        pnl_percent REAL DEFAULT 0.0,
        is_break_even INTEGER DEFAULT 0,
        partial_tp_taken INTEGER DEFAULT 0,
        trailing_sl_active INTEGER DEFAULT 0,
        status TEXT NOT NULL,            -- OPEN, CLOSED, CANCELLED
        open_time TEXT NOT NULL,
        close_time TEXT,
        close_price REAL,
        close_reason TEXT
    );
    """)

    # 4. Trading Journal Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trade_journal (
        id TEXT PRIMARY KEY,
        ticket TEXT NOT NULL,
        symbol TEXT NOT NULL,
        strategy_name TEXT NOT NULL,
        direction TEXT NOT NULL,
        entry_price REAL NOT NULL,
        exit_price REAL NOT NULL,
        stop_loss REAL NOT NULL,
        take_profit REAL NOT NULL,
        lots REAL NOT NULL,
        risk_percent REAL NOT NULL,
        net_profit REAL NOT NULL,
        risk_reward_achieved REAL NOT NULL,
        entry_time TEXT NOT NULL,
        exit_time TEXT NOT NULL,
        entry_reason TEXT NOT NULL,
        exit_reason TEXT NOT NULL,
        market_conditions TEXT,
        lessons_learned TEXT,
        tags TEXT                        -- JSON list of tags
    );
    """)

    # 5. Prop Firm Challenge State
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS prop_firm_state (
        id TEXT PRIMARY KEY,
        profile_name TEXT NOT NULL,
        starting_balance REAL NOT NULL,
        current_balance REAL NOT NULL,
        current_equity REAL NOT NULL,
        high_water_mark REAL NOT NULL,
        daily_start_balance REAL NOT NULL,
        daily_loss_limit_amount REAL NOT NULL,
        max_drawdown_limit_amount REAL NOT NULL,
        profit_target_amount REAL NOT NULL,
        trading_days_completed INTEGER DEFAULT 0,
        is_breached INTEGER DEFAULT 0,
        breach_reason TEXT,
        is_active INTEGER DEFAULT 1,
        last_updated TEXT NOT NULL
    );
    """)

    # 6. Audit Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        event_type TEXT NOT NULL,
        severity TEXT NOT NULL,          -- INFO, WARNING, CRITICAL
        message TEXT NOT NULL,
        details TEXT                     -- JSON details
    );
    """)

    # 7. System Settings
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)

    _seed_and_restore_users(cursor, conn)

    conn.commit()
    conn.close()

def _seed_and_restore_users(cursor: sqlite3.Cursor, conn: sqlite3.Connection):
    from werkzeug.security import generate_password_hash
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # Tracked seed file in backend/storage/ (persists in Git across Render deployments)
    git_seed_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users_seed.json")
    runtime_seed_file = os.path.join(base_dir, "data", "persisted_users.json")

    # 1. Restore from JSON backup if available
    for seed_path in [git_seed_file, runtime_seed_file]:
        if os.path.exists(seed_path):
            try:
                with open(seed_path, "r", encoding="utf-8") as f:
                    saved_users = json.load(f)
                for u in saved_users:
                    cursor.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)", (u.get("username"), u.get("email")))
                    if not cursor.fetchone():
                        cursor.execute(
                            "INSERT INTO users (id, username, email, password_hash, is_confirmed, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                            (u["id"], u["username"], u["email"], u["password_hash"], u.get("is_confirmed", 1), u.get("created_at", datetime.now().isoformat()))
                        )
                conn.commit()
            except Exception as e:
                print(f"[DB Warning] Could not restore persisted users from {seed_path}: {e}")

    # 2. Ensure default user amrit exists
    cursor.execute("SELECT id FROM users WHERE LOWER(username) = 'amrit' OR LOWER(email) = 'workingamrit123@gmail.com'")
    if not cursor.fetchone():
        default_pwd = generate_password_hash("AmritTrading2026!")
        cursor.execute(
            "INSERT INTO users (id, username, email, password_hash, is_confirmed, created_at) VALUES (?, ?, ?, ?, 1, ?)",
            ("usr_amrit_default", "amrit", "workingamrit123@gmail.com", default_pwd, datetime.now().isoformat())
        )
        conn.commit()

def persist_users_to_disk():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    git_seed_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users_seed.json")
    runtime_seed_file = os.path.join(base_dir, "data", "persisted_users.json")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, email, password_hash, is_confirmed, created_at FROM users")
        rows = cursor.fetchall()
        users_list = [dict(r) for r in rows]
        conn.close()

        for out_file in [git_seed_file, runtime_seed_file]:
            os.makedirs(os.path.dirname(out_file), exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(users_list, f, indent=2)
    except Exception as e:
        print(f"[DB Warning] Could not persist users: {e}")

def log_audit(event_type: str, severity: str, message: str, details: Optional[Dict[str, Any]] = None):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO audit_logs (timestamp, event_type, severity, message, details) VALUES (?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), event_type, severity, message, json.dumps(details or {}))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Audit Log Warning] Could not write audit log: {e}")
