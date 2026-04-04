"""
Agent Memory System
-------------------
Gives every agent persistent memory across sessions.
Uses SQLite - no extra services needed, runs on the G14.

Each agent gets its own memory space.
Shared memory is available to all agents.

Memory types:
- facts       : things the agent learned and wants to remember
- jobs        : jobs Scout has found (deduplication)
- contacts    : recruiters and people Outreach has found or messaged
- tasks       : task history with outcomes
- approvals   : record of what Katy approved or rejected
- notes       : free-form agent notes
"""

import sqlite3
import json
import os
from pathlib import Path as _Path
import sys as _sys
_sys.path.insert(0, str(_Path(__file__).parents[2]))
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(_Path(__file__).parents[2] / '.env', override=False)
except Exception:
    pass
from datetime import datetime
from pathlib import Path
from typing import Optional
from constants import MAX_PROSPECT_SCORE, ALLOWED_TARGET_NICHES

DB_PATH = Path(os.getenv("MEMORY_DB_PATH", "/app/memory/agent_memory.db"))

def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create all tables if they don't exist"""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(agent, key)
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            url TEXT,
            salary TEXT,
            location TEXT,
            match_score TEXT,
            notes TEXT,
            status TEXT DEFAULT 'found',
            found_at TEXT DEFAULT (datetime('now')),
            applied_at TEXT,
            UNIQUE(title, company)
        );

        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            title TEXT,
            company TEXT,
            platform TEXT,
            profile_url TEXT,
            email TEXT,
            status TEXT DEFAULT 'found',
            last_contacted TEXT,
            notes TEXT,
            found_at TEXT DEFAULT (datetime('now')),
            UNIQUE(name, company)
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL,
            task TEXT NOT NULL,
            result TEXT,
            status TEXT DEFAULT 'completed',
            started_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            decision TEXT,
            decided_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS prospects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_name TEXT NOT NULL,
            location TEXT,
            niche TEXT,
            phone TEXT,
            email TEXT,
            website TEXT,
            maps_url TEXT,
            owner_name TEXT,
            gbp_score REAL DEFAULT 0,
            gbp_issues TEXT,
            priority TEXT DEFAULT 'WARM',
            pipeline_stage TEXT DEFAULT 'found',
            audit_data TEXT,
            research_notes TEXT,
            outreach_draft TEXT,
            outreach_sent_at TEXT,
            followup_count INTEGER DEFAULT 0,
            last_followup_at TEXT,
            reply_received INTEGER DEFAULT 0,
            proposal_sent_at TEXT,
            deposit_paid INTEGER DEFAULT 0,
            deposit_amount REAL,
            final_paid INTEGER DEFAULT 0,
            final_amount REAL,
            stripe_deposit_link TEXT,
            stripe_invoice_url TEXT,
            found_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            notes TEXT,
            last_call_at TEXT,
            last_call_outcome TEXT,
            call_result_summary TEXT,
            call_temperature TEXT,
            objections TEXT,
            next_action TEXT,
            callback_due_at TEXT,
            callback_reason TEXT,
            callback_status TEXT DEFAULT 'pending',
            requires_human_transfer INTEGER DEFAULT 0,
            transfer_status TEXT,
            call_attempts INTEGER DEFAULT 0,
            UNIQUE(business_name, location)
        );

        CREATE TABLE IF NOT EXISTS katy_availability (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            available_now INTEGER DEFAULT 0,
            available_until TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS eric_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id TEXT UNIQUE,
            phone_number TEXT NOT NULL,
            company_name TEXT,
            contact_name TEXT,
            contact_email TEXT,
            call_outcome TEXT,
            interest_level TEXT,
            call_duration_seconds INTEGER DEFAULT 0,
            payment_status TEXT DEFAULT 'pending',
            payment_amount REAL DEFAULT 1000,
            stripe_checkout_url TEXT,
            stripe_session_id TEXT,
            stripe_payment_intent_id TEXT,
            payment_method TEXT,
            transfer_requested_at TEXT,
            transfer_accepted INTEGER DEFAULT 0,
            callback_scheduled_at TEXT,
            callback_time TEXT,
            notes TEXT,
            call_started_at TEXT DEFAULT (datetime('now')),
            call_ended_at TEXT,
            call_recording_url TEXT
        );

        CREATE TABLE IF NOT EXISTS dnc_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT NOT NULL UNIQUE,
            business_name TEXT,
            reason TEXT,
            source TEXT DEFAULT 'internal',
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
    """)

    prospect_columns = {
        "opt_out_at": "TEXT",
        "opt_out_reason": "TEXT",
        "dnc_status": "TEXT DEFAULT 'clear'",
        "dnc_checked_at": "TEXT",
        "dnc_source": "TEXT",
        "ai_call_written_consent": "INTEGER DEFAULT 0",
        "ai_call_express_consent": "INTEGER DEFAULT 0",
        "ai_call_consent_source": "TEXT",
        "ai_call_consent_notes": "TEXT",
        "ai_call_consent_updated_at": "TEXT",
    }
    existing_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(prospects)").fetchall()
    }
    for column_name, column_type in prospect_columns.items():
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE prospects ADD COLUMN {column_name} {column_type}")

    conn.commit()
    conn.close()
    print("✅ Memory database initialized")

# ── FACTS ────────────────────────────────────────────

def remember(agent: str, key: str, value: str):
    """Store or update a fact for an agent"""
    conn = get_db()
    conn.execute("""
        INSERT INTO facts (agent, key, value, updated_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(agent, key) DO UPDATE SET
            value=excluded.value,
            updated_at=datetime('now')
    """, (agent, key, value))
    conn.commit()
    conn.close()

def recall(agent: str, key: str) -> Optional[str]:
    """Get a fact for an agent"""
    conn = get_db()
    row = conn.execute(
        "SELECT value FROM facts WHERE agent=? AND key=?", (agent, key)
    ).fetchone()
    conn.close()
    return row["value"] if row else None

def recall_all(agent: str) -> dict:
    """Get all facts for an agent"""
    conn = get_db()
    rows = conn.execute(
        "SELECT key, value FROM facts WHERE agent=?", (agent,)
    ).fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}

# ── JOBS ─────────────────────────────────────────────

def save_job(title: str, company: str, url: str = None,
             salary: str = None, location: str = None,
             match_score: str = None, notes: str = None) -> bool:
    """Save a job. Returns True if new, False if already known."""
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO jobs (title, company, url, salary, location, match_score, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (title, company, url, salary, location, match_score, notes))
        conn.commit()
        conn.close()
        return True  # new job
    except sqlite3.IntegrityError:
        conn.close()
        return False  # already exists

def get_jobs(status: str = None) -> list:
    """Get all jobs, optionally filtered by status"""
    conn = get_db()
    if status:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status=? ORDER BY found_at DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY found_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_job_status(title: str, company: str, status: str):
    """Update job status: found | applied | interview | rejected | offer"""
    conn = get_db()
    conn.execute("""
        UPDATE jobs SET status=?, applied_at=CASE WHEN ?='applied'
        THEN datetime('now') ELSE applied_at END
        WHERE title=? AND company=?
    """, (status, status, title, company))
    conn.commit()
    conn.close()

def job_exists(title: str, company: str) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM jobs WHERE title=? AND company=?", (title, company)
    ).fetchone()
    conn.close()
    return row is not None

# ── CONTACTS ─────────────────────────────────────────

def save_contact(name: str, company: str, title: str = None,
                 platform: str = None, profile_url: str = None,
                 email: str = None, notes: str = None) -> bool:
    """Save a contact. Returns True if new."""
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO contacts (name, company, title, platform, profile_url, email, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, company, title, platform, profile_url, email, notes))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def get_contacts(status: str = None) -> list:
    conn = get_db()
    if status:
        rows = conn.execute(
            "SELECT * FROM contacts WHERE status=? ORDER BY found_at DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM contacts ORDER BY found_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def contact_exists(name: str, company: str) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM contacts WHERE name=? AND company=?", (name, company)
    ).fetchone()
    conn.close()
    return row is not None

def mark_contacted(name: str, company: str):
    conn = get_db()
    conn.execute("""
        UPDATE contacts SET status='contacted', last_contacted=datetime('now')
        WHERE name=? AND company=?
    """, (name, company))
    conn.commit()
    conn.close()

# ── TASKS ────────────────────────────────────────────

def log_task(agent: str, task: str, result: str = None, status: str = "completed"):
    conn = get_db()
    conn.execute("""
        INSERT INTO tasks (agent, task, result, status, completed_at)
        VALUES (?, ?, ?, ?, datetime('now'))
    """, (agent, task, result, status))
    conn.commit()
    conn.close()

def get_recent_tasks(agent: str = None, limit: int = 20) -> list:
    conn = get_db()
    if agent:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE agent=? ORDER BY started_at DESC LIMIT ?",
            (agent, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── NOTES ────────────────────────────────────────────

def add_note(agent: str, content: str, category: str = "general"):
    conn = get_db()
    conn.execute(
        "INSERT INTO notes (agent, category, content) VALUES (?, ?, ?)",
        (agent, category, content)
    )
    conn.commit()
    conn.close()

def get_notes(agent: str, category: str = None, limit: int = 10) -> list:
    conn = get_db()
    if category:
        rows = conn.execute(
            "SELECT * FROM notes WHERE agent=? AND category=? ORDER BY created_at DESC LIMIT ?",
            (agent, category, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM notes WHERE agent=? ORDER BY created_at DESC LIMIT ?",
            (agent, limit)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── SUMMARY ──────────────────────────────────────────

def get_memory_summary() -> dict:
    """Used by coordinator to brief Katy on what's been accumulated"""
    conn = get_db()
    jobs_total = conn.execute("SELECT COUNT(*) as c FROM jobs").fetchone()["c"]
    jobs_new = conn.execute("SELECT COUNT(*) as c FROM jobs WHERE status='found'").fetchone()["c"]
    jobs_applied = conn.execute("SELECT COUNT(*) as c FROM jobs WHERE status='applied'").fetchone()["c"]
    contacts_total = conn.execute("SELECT COUNT(*) as c FROM contacts").fetchone()["c"]
    contacts_new = conn.execute("SELECT COUNT(*) as c FROM contacts WHERE status='found'").fetchone()["c"]
    tasks_today = conn.execute(
        "SELECT COUNT(*) as c FROM tasks WHERE date(started_at)=date('now')"
    ).fetchone()["c"]
    conn.close()
    return {
        "jobs_total": jobs_total,
        "jobs_new": jobs_new,
        "jobs_applied": jobs_applied,
        "contacts_total": contacts_total,
        "contacts_new_uncontacted": contacts_new,
        "tasks_today": tasks_today,
    }

# ── PROSPECTS (GBP Sales Pipeline) ───────────────────

def save_prospect(business_name: str, location: str, **kwargs) -> bool:
    """Save a GBP prospect. Returns True if new. Also pushes to Google Sheets."""
    # Hard gate: do not persist businesses outside approved target niches.
    niche = kwargs.get("niche")
    if niche is not None:
        allowed_niches = {n.lower() for n in ALLOWED_TARGET_NICHES}
        if str(niche).strip().lower() not in allowed_niches:
            return False

    # Hard gate: do not persist businesses with scores above threshold.
    score = kwargs.get("gbp_score")
    if score is not None:
        try:
            if float(score) > MAX_PROSPECT_SCORE:
                return False
        except (TypeError, ValueError):
            pass

    conn = get_db()
    # Serialize dict fields
    for field in ("gbp_issues", "audit_data"):
        if field in kwargs and isinstance(kwargs[field], (list, dict)):
            kwargs[field] = json.dumps(kwargs[field])
    fields = ["business_name", "location"] + list(kwargs.keys())
    placeholders = ", ".join(["?"] * len(fields))
    values = [business_name, location] + list(kwargs.values())
    try:
        conn.execute(
            f"INSERT INTO prospects ({', '.join(fields)}) VALUES ({placeholders})",
            values
        )
        conn.commit()
        conn.close()
        # Push to Google Sheets (gspread service account)
        try:
            from tools.sheets_tool import push_prospect_sync
            prospect_data = {"business_name": business_name, "location": location, **kwargs}
            push_prospect_sync(prospect_data)
        except Exception as e:
            print(f"[Memory] Sheets sync failed for {business_name}: {e}")
        return True
    except Exception:
        conn.close()
        return False


def update_prospect(business_name: str, location: str, **kwargs):
    """Update fields on an existing prospect."""
    conn = get_db()
    for field in ("gbp_issues", "audit_data"):
        if field in kwargs and isinstance(kwargs[field], (list, dict)):
            kwargs[field] = json.dumps(kwargs[field])
    if not kwargs:
        conn.close()
        return
    set_clause = ", ".join(f"{k}=?" for k in kwargs.keys())
    set_clause += ", updated_at=datetime('now')"
    values = list(kwargs.values()) + [business_name, location]
    conn.execute(
        f"UPDATE prospects SET {set_clause} WHERE business_name=? AND location=?",
        values
    )
    conn.commit()
    conn.close()


def get_prospects(stage: str = None, priority: str = None, limit: int = 50) -> list:
    conn = get_db()
    query = "SELECT * FROM prospects WHERE 1=1"
    params = []
    if stage:
        query += " AND pipeline_stage=?"
        params.append(stage)
    if priority:
        query += " AND priority=?"
        params.append(priority)
    query += " ORDER BY found_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_prospect(business_name: str, location: str) -> Optional[dict]:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM prospects WHERE business_name=? AND location=?",
        (business_name, location)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def cleanup_prospects_by_policy(dry_run: bool = True) -> dict:
    """
    Remove prospects that violate current targeting policy.
    Policy:
    - niche must be in ALLOWED_TARGET_NICHES
    - gbp_score must be <= MAX_PROSPECT_SCORE
    """
    conn = get_db()

    allowed = [n.lower() for n in ALLOWED_TARGET_NICHES]
    placeholders = ", ".join(["?"] * len(allowed))

    where_clause = (
        f"COALESCE(LOWER(TRIM(niche)), '') NOT IN ({placeholders}) "
        "OR COALESCE(gbp_score, 999) > ?"
    )
    params = [*allowed, MAX_PROSPECT_SCORE]

    rows = conn.execute(
        f"SELECT id, business_name, location, niche, gbp_score FROM prospects WHERE {where_clause}",
        params,
    ).fetchall()

    total_violations = len(rows)
    deleted = 0

    if not dry_run and total_violations:
        conn.execute(f"DELETE FROM prospects WHERE {where_clause}", params)
        conn.commit()
        deleted = total_violations

    sample = [dict(r) for r in rows[:25]]
    conn.close()

    return {
        "dry_run": dry_run,
        "policy": {
            "allowed_niches": ALLOWED_TARGET_NICHES,
            "max_score": MAX_PROSPECT_SCORE,
        },
        "violations_found": total_violations,
        "deleted": deleted,
        "sample": sample,
    }


# ── KATY AVAILABILITY ───────────────────────
def get_availability() -> dict:
    """Get current availability state."""
    conn = get_db()
    row = conn.execute("SELECT * FROM katy_availability WHERE id=1").fetchone()
    conn.close()
    if row:
        return {
            "available_now": bool(row["available_now"]),
            "available_until": row["available_until"],
            "updated_at": row["updated_at"]
        }
    return {"available_now": False, "available_until": None, "updated_at": None}

def set_availability(available_now: bool, available_until: str = None):
    """Set Katy's availability state."""
    conn = get_db()
    conn.execute("""
        INSERT OR REPLACE INTO katy_availability (id, available_now, available_until, updated_at)
        VALUES (1, ?, ?, datetime('now'))
    """, (1 if available_now else 0, available_until))
    conn.commit()
    conn.close()

# Initialize on import
init_db()
