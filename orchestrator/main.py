from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import uvicorn, json, os, asyncio, re
from datetime import datetime, timezone
from pathlib import Path
import httpx

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

# ── Google Service Account credentials ──────────────────────────────────────
import base64, tempfile
_gac = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
if _gac:
    try:
        _decoded = base64.b64decode(_gac).decode('utf-8')
        _tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        _tmp.write(_decoded)
        _tmp.close()
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = _tmp.name
        print(f'Google credentials loaded -> {_tmp.name}')
    except Exception as _e:
        print(f'Warning: Could not load GOOGLE_APPLICATION_CREDENTIALS_JSON: {_e}')
# ────────────────────────────────────────────────────────────────────────────

from agents.coordinator import CoordinatorAgent
from agents.research import ResearchAgent
from agents.research_assistant import ResearchAssistantAgent
from agents.small_biz_expert import SmallBizExpertAgent
from agents.sales import SalesAgent, SalesOpsAgent
from agents.outreach import OutreachAgent
from agents.engineer import EngineerAgent
from agents.team_leader import TeamLeaderAgent
from agents.networking import NetworkingAgent
from agents.lead_gen import LeadGenAgent
from agents.marketing import MarketingAgent
from agents.biz_dev import BizDevAgent
from agents.automations import AutomationsAgent
from agents.solutions_architect import SolutionsArchitectAgent
from agents.gbp_scout import GBPScoutAgent
from agents.gbp_researcher import GBPResearcherAgent
from agents.gbp_sales import GBPSalesAgent
from agents.closer import CloserAgent
from agents.demo_agent import DemoAgent
from scheduler import scheduler
from memory.memory import init_db, get_memory_summary
from task_handler import TaskHandler
from playbooks import PlaybookRunner
from constants import ALLOWED_TARGET_NICHES, DEFAULT_TARGET_NICHE, MAX_PROSPECT_SCORE

_BASE = Path(os.getenv("APP_BASE", Path(__file__).parent))
MEMORY_PATH = Path(os.getenv("MEMORY_DB_PATH", _BASE / "memory" / "katy_brief.md")).parent / "katy_brief.md"
KATY_BRIEF = MEMORY_PATH.read_text() if MEMORY_PATH.exists() else ""
LOG_DIR = Path(os.getenv("LOG_DIR", _BASE / "logs"))
LOG_DIR.mkdir(exist_ok=True)
COMPLIANCE_LOG_DIR = LOG_DIR / "compliance"
COMPLIANCE_LOG_DIR.mkdir(exist_ok=True)

event_stream = []
approval_queue = []
scheduled_events = []
scheduled_events_lock = asyncio.Lock()
scheduled_events_runner = None

# Full agent roster
AGENT_MAP = {
    # ── Prospecting & Research ────────────────────────────
    "gbp_scout":            lambda b,l,a: GBPScoutAgent(b,l,a),
    "gbp_researcher":       lambda b,l,a: GBPResearcherAgent(b,l,a),
    "lead_gen":             lambda b,l,a: LeadGenAgent(b,l,a),
    "research":             lambda b,l,a: ResearchAgent(b,l,a),
    "research_assistant":   lambda b,l,a: ResearchAssistantAgent(b,l,a),
    "small_biz_expert":     lambda b,l,a: SmallBizExpertAgent(b,l,a),
    # ── Outreach & Relationships ──────────────────────────
    "outreach":             lambda b,l,a: OutreachAgent(b,l,a),
    "networking":           lambda b,l,a: NetworkingAgent(b,l,a),
    # ── Sales & Closing ───────────────────────────────────
    "sales":                lambda b,l,a: SalesAgent(b,l,a),
    "sales_ops":            lambda b,l,a: SalesOpsAgent(b,l,a),
    "gbp_sales":            lambda b,l,a: GBPSalesAgent(b,l,a),
    "closer":               lambda b,l,a: CloserAgent(b,l,a),
    "demo":                 lambda b,l,a: DemoAgent(b,l,a),
    # ── Strategy & Marketing ──────────────────────────────
    "marketing":            lambda b,l,a: MarketingAgent(b,l,a),
    "biz_dev":              lambda b,l,a: BizDevAgent(b,l,a),
    "automations":          lambda b,l,a: AutomationsAgent(b,l,a),
    "solutions_architect":  lambda b,l,a: SolutionsArchitectAgent(b,l,a),
    # ── Infrastructure ────────────────────────────────────
    "engineer":             lambda b,l,a: EngineerAgent(b,l,a),
    "team_leader":          lambda b,l,a: TeamLeaderAgent(b,l,a),
    "coordinator":          lambda b,l,a: CoordinatorAgent(b,l,a),
}

def log_event(agent: str, event_type: str, content: str):
    event = {"id": len(event_stream)+1, "timestamp": datetime.now().isoformat(),
             "agent": agent, "type": event_type, "content": content}
    event_stream.append(event)
    with open(LOG_DIR / "events.jsonl", "a") as f:
        f.write(json.dumps(event) + "\n")
    return event


def _write_jsonl(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def log_compliance_event(category: str, event_type: str, details: dict):
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "category": category,
        "type": event_type,
        "details": details,
    }
    _write_jsonl(COMPLIANCE_LOG_DIR / f"{category}.jsonl", event)
    return event


def _prospect_is_blocked_by_compliance(prospect: dict) -> tuple[bool, str]:
    if not prospect:
        return False, ""
    if str(prospect.get("next_action", "")).strip().lower() == "do_not_call":
        return True, "next_action=do_not_call"
    if str(prospect.get("dnc_status", "")).strip().lower() in {"internal_opt_out", "dnc", "revoked", "blocked"}:
        return True, f"dnc_status={prospect.get('dnc_status')}"
    if prospect.get("opt_out_at"):
        return True, "opted_out"
    return False, ""


def _lookup_dnc_entry(phone: str) -> dict:
    normalized = _normalize_phone(phone)
    if not normalized:
        return {}
    from memory.memory import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM dnc_entries WHERE phone_number=?",
        (normalized,),
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


def _dnc_scrub(phone: str, business_name: str = "", prospect: dict | None = None) -> tuple[bool, str]:
    blocked, reason = _prospect_is_blocked_by_compliance(prospect or {})
    if blocked:
        return True, reason
    dnc_entry = _lookup_dnc_entry(phone)
    if dnc_entry:
        return True, f"dnc_list:{dnc_entry.get('reason') or dnc_entry.get('source') or 'blocked'}"
    return False, ""


def _record_dnc_entry(phone: str, business_name: str, reason: str, source: str = "internal_opt_out", notes: str = ""):
    normalized = _normalize_phone(phone)
    if not normalized:
        return
    from memory.memory import get_db
    conn = get_db()
    conn.execute(
        """
        INSERT INTO dnc_entries (phone_number, business_name, reason, source, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        ON CONFLICT(phone_number) DO UPDATE SET
            business_name=excluded.business_name,
            reason=excluded.reason,
            source=excluded.source,
            notes=excluded.notes,
            updated_at=datetime('now')
        """,
        (normalized, business_name, reason, source, notes),
    )
    conn.commit()
    conn.close()
    log_compliance_event("dnc", "added", {
        "phone_number": normalized,
        "business_name": business_name,
        "reason": reason,
        "source": source,
        "notes": notes,
    })

# Actions that auto-send after 30 min if not rejected (replies to people who reached out first)
_AUTO_APPROVE_ACTIONS = {"send_sms_reply", "send_email_reply"}

# Actions that NEVER auto-send — always need explicit YES
_MANUAL_ONLY_ACTIONS  = {
    "send_outreach_message", "send_sales_proposal", "send_answering_service_proposal",
    "send_close_message", "send_demo_message", "send_connection_or_message",
    "send_connection_request", "publish_content",
}

AUTO_APPROVE_MINUTES = int(os.getenv("AUTO_APPROVE_MINUTES", "30"))


def request_approval(agent: str, action: str, details: dict):
    item = {
        "id": len(approval_queue) + 1,
        "timestamp": datetime.now().isoformat(),
        "agent": agent,
        "action": action,
        "details": details,
        "status": "pending",
    }

    # For auto-approvable actions, set a deadline
    if action in _AUTO_APPROVE_ACTIONS:
        send_at = datetime.now(timezone.utc) + timedelta(minutes=AUTO_APPROVE_MINUTES)
        item["send_at"] = send_at.isoformat()
        item["auto_approve"] = True

    approval_queue.append(item)
    log_event(agent, "approval_needed", f"{action}: {json.dumps(details)}")

    # Fire-and-forget Telegram notification (non-blocking)
    asyncio.get_event_loop().call_soon_threadsafe(
        lambda: asyncio.ensure_future(_notify_approval_telegram(item))
    )
    return item


async def _notify_approval_telegram(item: dict):
    """Send Telegram notification for a new approval item."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    katy_id   = os.getenv("KATY_TELEGRAM_ID", "")
    if not bot_token or not katy_id:
        return

    details = item.get("details", {})
    action  = item.get("action", "")
    item_id = item.get("id", "?")

    # Build a human-readable preview
    preview = (
        details.get("draft_reply")
        or details.get("draft_preview")
        or details.get("preview")
        or str(details)[:200]
    )

    if item.get("auto_approve"):
        footer = (
            f"\n⏱ <b>Auto-sends in {AUTO_APPROVE_MINUTES} min</b> unless you cancel.\n"
            f"Reply /no {item_id} to cancel."
        )
    else:
        footer = f"\n/approve {item_id}  •  /no {item_id}"

    business = details.get("business") or details.get("business_name") or ""
    to       = details.get("to") or ""

    msg = (
        f"📋 <b>Approval #{item_id}</b> — {action.replace('_', ' ')}\n"
        + (f"For: {business}" + (f" ({to})" if to else "") + "\n" if business or to else "")
        + f"\n{preview[:400]}"
        + footer
    )

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": katy_id, "text": msg, "parse_mode": "HTML"},
            )
    except Exception as e:
        log_event("system", "warn", f"Approval Telegram notify failed: {e}")


async def _execute_approval(item: dict):
    """Execute an approved action — called on explicit approve OR auto-approve timeout."""
    action  = item.get("action", "")
    details = item.get("details", {})

    if action == "send_sms_reply":
        to    = details.get("to", "")
        draft = details.get("draft_reply", "")
        if to and draft:
            try:
                from tools.sms_tool import send_sms
                result = send_sms(to_number=to, body=draft[:160])
                item["send_result"] = result
                log_event("sales", "action", f"SMS reply sent to {to}: {result.get('sent')}")
            except Exception as e:
                log_event("sales", "warn", f"SMS send failed: {e}")

    elif action == "send_email_reply":
        to      = details.get("to", "")
        subject = f"Re: {details.get('their_subject', 'Following up')}"
        draft   = details.get("draft_reply", "")
        if to and draft:
            try:
                from tools.gmail_tool import send_email
                result = send_email(to=to, subject=subject, body=draft)
                item["send_result"] = result
                log_event("sales", "action", f"Email reply sent to {to}: {result.get('sent')}")
            except Exception as e:
                log_event("sales", "warn", f"Email send failed: {e}")


async def _auto_approve_worker():
    """Background task: checks every 2 min for timed-out approval items and executes them."""
    while True:
        await asyncio.sleep(120)
        now = datetime.now(timezone.utc)
        for item in approval_queue:
            if item.get("status") != "pending":
                continue
            if not item.get("auto_approve"):
                continue
            send_at_str = item.get("send_at", "")
            if not send_at_str:
                continue
            try:
                send_at = datetime.fromisoformat(send_at_str)
                if send_at.tzinfo is None:
                    send_at = send_at.replace(tzinfo=timezone.utc)
                if now >= send_at:
                    item["status"] = "auto_approved"
                    log_event("system", "action", f"Auto-approved #{item['id']}: {item['action']}")
                    await _execute_approval(item)
            except Exception as e:
                log_event("system", "warn", f"Auto-approve worker error: {e}")


SCHEDULED_EVENTS_PATH = LOG_DIR / "scheduled_events.json"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_schedule_time(value) -> datetime:
    if value is None:
        raise ValueError("Missing run_at")

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)

    raw = str(value).strip()
    if not raw:
        raise ValueError("Missing run_at")

    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo
        dt = dt.replace(tzinfo=local_tz)

    return dt.astimezone(timezone.utc)


def _save_scheduled_events():
    with open(SCHEDULED_EVENTS_PATH, "w") as f:
        json.dump(scheduled_events, f, indent=2)


def _load_scheduled_events():
    if not SCHEDULED_EVENTS_PATH.exists():
        return
    try:
        loaded = json.loads(SCHEDULED_EVENTS_PATH.read_text())
        if isinstance(loaded, list):
            scheduled_events.extend(loaded)
    except Exception as e:
        log_event("system", "thought", f"Could not load scheduled events: {e}")


def _serialize_scheduled_event(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "agent": item.get("agent"),
        "task": item.get("task"),
        "status": item.get("status"),
        "run_at": item.get("run_at"),
        "created_at": item.get("created_at"),
        "started_at": item.get("started_at"),
        "completed_at": item.get("completed_at"),
        "error": item.get("error", ""),
        "result_preview": item.get("result_preview", ""),
    }


async def _execute_agent_task(agent_name: str, task: str) -> str:
    log_event(agent_name, "thought", f"Starting: {task}")

    if agent_name == "coordinator":
        handler = make_task_handler()
        agent = CoordinatorAgent(KATY_BRIEF, log_event, request_approval,
                                 dispatch_fn=handler.dispatch)
    else:
        factory = AGENT_MAP.get(agent_name)
        if not factory:
            raise ValueError(f"Unknown agent: {agent_name}")
        agent = factory(KATY_BRIEF, log_event, request_approval)

    result = await agent.run(task)
    log_event(agent_name, "result", result[:300])
    return result


def _extract_json_prospects_blob(text: str) -> list[dict]:
    if not text:
        return []
    m = re.search(r"<prospects_json>\s*(.*?)\s*</prospects_json>", text, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return []
    raw = m.group(1).strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            parsed = [parsed]
        if isinstance(parsed, list):
            return [p for p in parsed if isinstance(p, dict)]
    except Exception:
        return []
    return []


def _extract_text_prospects_fallback(text: str) -> list[dict]:
    if not text:
        return []

    chunks = [c.strip() for c in re.split(r"\n\s*\n", text) if c.strip()]
    prospects = []

    for chunk in chunks:
        lower = chunk.lower()
        if not any(token in lower for token in ["priority", "name", "company", "business", "why", "reach"]):
            continue

        lines = [ln.strip(" -*\t") for ln in chunk.splitlines() if ln.strip()]
        if not lines:
            continue

        first_line = lines[0]
        name = ""
        location = ""
        priority = "WARM"

        m_name = re.search(r"(?:name\s*/\s*company|company|business|name)\s*:\s*(.+)$", chunk, flags=re.IGNORECASE | re.MULTILINE)
        if m_name:
            name = m_name.group(1).strip()
        else:
            name = re.sub(r"^\d+[\.)]\s*", "", first_line).strip()

        m_loc = re.search(r"location\s*:\s*(.+)$", chunk, flags=re.IGNORECASE | re.MULTILINE)
        if m_loc:
            location = m_loc.group(1).strip()
        else:
            m_paren = re.search(r"\(([^\)]+)\)", first_line)
            if m_paren:
                location = m_paren.group(1).strip()

        m_pri = re.search(r"\b(HOT|WARM|COLD)\b", chunk, flags=re.IGNORECASE)
        if m_pri:
            priority = m_pri.group(1).upper()

        email_match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", chunk, flags=re.IGNORECASE)
        website_match = re.search(r"https?://[^\s)]+", chunk, flags=re.IGNORECASE)
        phone_match = re.search(r"(?:\+?1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}", chunk)

        why_fit = ""
        approach = ""
        m_why = re.search(r"why\s+(?:they\s+are\s+)?a\s+good\s+fit\s*:\s*(.+)$", chunk, flags=re.IGNORECASE | re.MULTILINE)
        if m_why:
            why_fit = m_why.group(1).strip()
        m_appr = re.search(r"suggested\s+first\s+approach\s*:\s*(.+)$", chunk, flags=re.IGNORECASE | re.MULTILINE)
        if m_appr:
            approach = m_appr.group(1).strip()

        cleaned_name = re.sub(r"\s*\([^\)]*\)\s*", " ", name).strip(" -")
        if len(cleaned_name) < 3:
            continue

        prospects.append({
            "business_name": cleaned_name,
            "location": location,
            "phone": phone_match.group(0).strip() if phone_match else "",
            "email": email_match.group(0).strip() if email_match else "",
            "website": website_match.group(0).strip() if website_match else "",
            "priority": priority,
            "research_notes": why_fit,
            "notes": approach,
        })

    return prospects


def _normalize_parsed_prospects(items: list[dict]) -> list[dict]:
    out = []
    seen = set()

    for raw in items:
        business_name = str(raw.get("business_name") or raw.get("company") or raw.get("name") or "").strip()
        if not business_name:
            continue

        location = str(raw.get("location") or "").strip()
        niche = str(raw.get("niche") or DEFAULT_TARGET_NICHE).strip().lower()
        if not _is_allowed_niche(niche):
            niche = DEFAULT_TARGET_NICHE

        priority = str(raw.get("priority") or "WARM").strip().upper()
        if priority not in {"HOT", "WARM", "COLD"}:
            priority = "WARM"

        key = (business_name.lower(), location.lower())
        if key in seen:
            continue
        seen.add(key)

        notes_parts = [
            str(raw.get("notes") or "").strip(),
            str(raw.get("suggested_first_approach") or "").strip(),
            str(raw.get("how_to_reach") or "").strip(),
        ]
        notes = " | ".join([p for p in notes_parts if p])[:900]

        out.append({
            "business_name": business_name,
            "location": location,
            "niche": niche,
            "phone": str(raw.get("phone") or "").strip(),
            "email": str(raw.get("email") or "").strip(),
            "website": str(raw.get("website") or "").strip(),
            "owner_name": str(raw.get("owner_name") or "").strip(),
            "priority": priority,
            "pipeline_stage": "found",
            "gbp_score": 3.0,
            "research_notes": str(raw.get("research_notes") or raw.get("why_fit") or "").strip()[:1200],
            "notes": notes,
        })

    return out


def _normalize_sheet_import_rows(items: list[dict]) -> list[dict]:
    normalized = []
    for raw in items:
        if not isinstance(raw, dict):
            continue

        business_name = str(
            raw.get("business_name")
            or raw.get("Business Name")
            or raw.get("company")
            or raw.get("Company")
            or raw.get("name")
            or raw.get("Name")
            or ""
        ).strip()
        if not business_name:
            continue

        location = str(
            raw.get("location")
            or raw.get("Location")
            or raw.get("city_state")
            or raw.get("City/State")
            or raw.get("address")
            or raw.get("Address")
            or ""
        ).strip()
        if not location:
            city = str(raw.get("city") or raw.get("City") or "").strip()
            state = str(raw.get("state") or raw.get("State") or "").strip()
            location = " ".join(part for part in [city, state] if part).strip()
        if not location:
            location = "Unknown"

        niche = str(raw.get("niche") or raw.get("Niche") or DEFAULT_TARGET_NICHE).strip().lower()
        if not _is_allowed_niche(niche):
            niche = DEFAULT_TARGET_NICHE

        priority = str(raw.get("priority") or raw.get("Priority") or "WARM").strip().upper()
        if priority not in {"HOT", "WARM", "COLD"}:
            priority = "WARM"

        score_raw = raw.get("buyer_intent_score")
        if score_raw is None:
            score_raw = raw.get("Buyer Intent Score")
        if score_raw is None:
            score_raw = raw.get("gbp_score")
        if score_raw is None:
            score_raw = raw.get("GBP Score")
        try:
            score = min(float(score_raw), MAX_PROSPECT_SCORE)
        except (TypeError, ValueError):
            score = 3.0

        notes_parts = [
            str(raw.get("notes") or raw.get("Notes") or "").strip(),
            str(raw.get("issues") or raw.get("Issues") or "").strip(),
            str(raw.get("source") or raw.get("Source") or "google_sheets_import").strip(),
        ]

        normalized.append({
            "business_name": business_name,
            "location": location,
            "niche": niche,
            "phone": str(raw.get("phone") or raw.get("Phone") or "").strip(),
            "email": str(raw.get("email") or raw.get("Email") or "").strip(),
            "website": str(raw.get("website") or raw.get("Website") or "").strip(),
            "owner_name": str(raw.get("owner_name") or raw.get("Owner Name") or "").strip(),
            "priority": priority,
            "pipeline_stage": "imported_sheet",
            "gbp_score": score,
            "research_notes": str(raw.get("research_notes") or raw.get("Research Notes") or "").strip()[:1200],
            "notes": " | ".join([part for part in notes_parts if part])[:900],
        })

    return _normalize_parsed_prospects(normalized)


async def _deep_dive_prospect_rows(rows: list[dict], limit: int = 5) -> dict:
    from memory.memory import update_prospect
    from tools.gbp_audit import lookup_phone_number

    processed = 0
    enriched_phone = 0
    for item in rows[:max(0, min(limit, 10))]:
        task = (
            "Deep-dive this service business prospect for AI answering-service fit. "
            f"Business: {item.get('business_name', '')}. "
            f"Location: {item.get('location', '')}. "
            f"Niche: {item.get('niche', '')}. "
            f"Website: {item.get('website', '')}. "
            f"Current notes: {item.get('notes', '')}. "
            "Return concise research covering likely missed-call pain, likely buyer intent, and a first outreach angle."
        )
        try:
            result = await _execute_agent_task("small_biz_expert", task)
        except Exception as e:
            result = f"Deep dive failed: {e}"

        updates = {
            "research_notes": str(result).strip()[:1500],
            "pipeline_stage": "researched",
        }
        if not item.get("phone"):
            try:
                phone = await lookup_phone_number(item["business_name"], item["location"], website=item.get("website", ""))
            except Exception:
                phone = ""
            if phone:
                updates["phone"] = str(phone).strip()
                enriched_phone += 1

        update_prospect(item["business_name"], item["location"], **updates)
        processed += 1

    return {"deep_dived": processed, "enriched_phone": enriched_phone}


async def _persist_prospects_from_result(agent_name: str, result_text: str) -> dict:
    from memory.memory import save_prospect, update_prospect

    if agent_name not in {"lead_gen", "coordinator", "team_leader"}:
        return {"parsed": 0, "saved": 0, "updated": 0, "enriched_phone": 0}

    parsed = _extract_json_prospects_blob(result_text)
    if not parsed:
        parsed = _extract_text_prospects_fallback(result_text)

    rows = _normalize_parsed_prospects(parsed)
    if not rows:
        return {"parsed": 0, "saved": 0, "updated": 0, "enriched_phone": 0}

    saved = 0
    updated = 0
    enriched_phone = 0

    from tools.gbp_audit import lookup_phone_number

    for item in rows:
        is_new = save_prospect(item["business_name"], item["location"], **{k: v for k, v in item.items() if k not in {"business_name", "location"}})
        if is_new:
            saved += 1
        else:
            # If it already exists, still refresh fields if we got better data.
            update_fields = {}
            for k in ["owner_name", "phone", "email", "website", "priority", "research_notes", "notes", "niche"]:
                val = item.get(k)
                if isinstance(val, str):
                    val = val.strip()
                if val:
                    update_fields[k] = val
            if update_fields:
                update_prospect(item["business_name"], item["location"], **update_fields)
                updated += 1

        # Lightweight deeper research pass: fill missing phone now if possible.
        if not item.get("phone"):
            try:
                found_phone = await lookup_phone_number(item["business_name"], item["location"], website=item.get("website", ""))
            except Exception:
                found_phone = ""
            if found_phone:
                update_prospect(item["business_name"], item["location"], phone=str(found_phone).strip(), pipeline_stage="researched")
                enriched_phone += 1

    if saved or updated or enriched_phone:
        log_event(
            "system",
            "action",
            f"Prospect import from {agent_name}: parsed={len(rows)} saved={saved} updated={updated} enriched_phone={enriched_phone}",
        )

    return {"parsed": len(rows), "saved": saved, "updated": updated, "enriched_phone": enriched_phone}


async def _run_scheduled_event(event_id: int):
    async with scheduled_events_lock:
        item = next((evt for evt in scheduled_events if evt.get("id") == event_id), None)
        if not item:
            return
        agent_name = item.get("agent", "coordinator")
        task = item.get("task", "")

    try:
        result = await _execute_agent_task(agent_name, task)
        async with scheduled_events_lock:
            item["status"] = "completed"
            item["completed_at"] = _now_utc().isoformat()
            item["result_preview"] = str(result)[:400]
            _save_scheduled_events()
        log_event("system", "action", f"Scheduled trigger #{event_id} completed")
    except Exception as e:
        async with scheduled_events_lock:
            item["status"] = "failed"
            item["completed_at"] = _now_utc().isoformat()
            item["error"] = str(e)
            _save_scheduled_events()
        log_event("system", "thought", f"Scheduled trigger #{event_id} failed: {e}")


async def _scheduled_events_loop():
    while True:
        try:
            now = _now_utc()
            due_event_ids = []

            async with scheduled_events_lock:
                for item in scheduled_events:
                    if item.get("status") != "scheduled":
                        continue
                    run_at_raw = item.get("run_at")
                    try:
                        run_at_dt = _parse_schedule_time(run_at_raw)
                    except Exception:
                        item["status"] = "failed"
                        item["completed_at"] = _now_utc().isoformat()
                        item["error"] = f"Invalid run_at: {run_at_raw}"
                        continue

                    if run_at_dt <= now:
                        item["status"] = "running"
                        item["started_at"] = now.isoformat()
                        due_event_ids.append(item.get("id"))

                if due_event_ids:
                    _save_scheduled_events()

            for event_id in due_event_ids:
                asyncio.create_task(_run_scheduled_event(event_id))

        except Exception as e:
            log_event("system", "thought", f"Scheduled-event loop error: {e}")

        await asyncio.sleep(2)


def _normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def _phones_match(left: str, right: str) -> bool:
    normalized_left = _normalize_phone(left)
    normalized_right = _normalize_phone(right)
    return bool(normalized_left and normalized_right and normalized_left == normalized_right)


def _parse_gbp_issues(raw_issues) -> list:
    if isinstance(raw_issues, list):
        return raw_issues
    if isinstance(raw_issues, str):
        try:
            parsed = json.loads(raw_issues)
            if isinstance(parsed, list):
                return parsed
            if parsed:
                return [str(parsed)]
        except Exception:
            return [raw_issues] if raw_issues else []
    return []


def _infer_gbp_condition(issues: list) -> str:
    if not issues:
        return "INCOMPLETE_PROFILE"
    issues_text = " ".join(issues).lower()
    if any(token in issues_text for token in ["no gbp", "no listing", "no profile", "unclaimed"]):
        return "NO_PROFILE"
    if "outdated" in issues_text:
        return "OUTDATED_PROFILE"
    if any(token in issues_text for token in ["incorrect", "wrong", "mismatch"]):
        return "INCORRECT_PROFILE"
    return "INCOMPLETE_PROFILE"


def _build_vapi_call_spec(body: dict, prospect_data: dict) -> dict:
    issues = body.get("issues") or _parse_gbp_issues(prospect_data.get("gbp_issues", "[]"))
    research = prospect_data.get("research_notes", "") or ""
    return {
        "prospect_phone": body.get("prospect_phone") or prospect_data.get("phone", ""),
        "prospect_name": body.get("prospect_name") or prospect_data.get("owner_name") or "the owner",
        "business_name": body.get("business_name") or prospect_data.get("business_name", ""),
        "gbp_condition": body.get("gbp_condition") or _infer_gbp_condition(issues),
        "issues": issues,
        "business_type": body.get("business_type") or prospect_data.get("niche", ""),
        "city": body.get("city") or prospect_data.get("location", ""),
        "website": body.get("website") or prospect_data.get("website", ""),
        "description": body.get("description") or research[:300],
        "years_in_business": body.get("years_in_business") or prospect_data.get("years_in_business", ""),
        "services": body.get("services") or prospect_data.get("services", ""),
        "rating": str(body.get("rating") or prospect_data.get("rating", "") or prospect_data.get("gbp_score", "")),
        "review_count": str(body.get("review_count") or prospect_data.get("review_count", "")),
        "extra_intel": body.get("extra_intel") or prospect_data.get("extra_intel", ""),
        "assistant_id": body.get("assistant_id", os.getenv("VAPI_ASSISTANT_ID", "")),
        "phone_number_id": body.get("phone_number_id", os.getenv("VAPI_PHONE_NUMBER_ID", "")),
    }


def _find_matching_prospect(prospect_phone: str, prospects: list) -> dict:
    if not prospect_phone:
        return {}
    return next((p for p in prospects if _phones_match(prospect_phone, p.get("phone", ""))), {})


def _prospect_text_blob(prospect: dict) -> str:
    return " ".join([
        str(prospect.get("business_name", "")),
        str(prospect.get("niche", "")),
        str(prospect.get("services", "")),
        str(prospect.get("research_notes", "")),
    ]).lower()


def _keyword_match(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _is_allowed_niche(niche: str) -> bool:
    val = str(niche or "").strip().lower()
    return val in {n.lower() for n in ALLOWED_TARGET_NICHES}


def _prospect_score(prospect: dict) -> float:
    try:
        return float(prospect.get("gbp_score", 999))
    except (TypeError, ValueError):
        return 999.0


def _eric_calling_enabled() -> bool:
    """Outbound calling is disabled by default until explicitly enabled."""
    val = str(os.getenv("ENABLE_ERIC_CALLS", "false")).strip().lower()
    return val in {"1", "true", "yes", "on"}


INTENT_TERMS = {
    "24/7", "24 hour", "24-hour", "emergency", "urgent", "same day", "same-day",
    "after hours", "after-hours", "dispatch", "call now", "immediate service",
    "service call", "book now", "on call", "rapid response", "fast response",
    "available now", "weekend service", "missed calls", "missed call", "voicemail",
}


def _intent_score(prospect: dict) -> int:
    text = _prospect_text_blob(prospect)
    score = sum(1 for term in INTENT_TERMS if term in text)
    niche = str(prospect.get("niche", "")).lower()
    if any(k in niche for k in ["plumb", "hvac", "electric", "locksmith", "towing", "garage", "roof"]):
        score += 1
    return score


def _is_legacy_profile_opportunity(prospect: dict) -> bool:
    issues = str(prospect.get("gbp_issues", "") or "").lower()
    return any(token in issues for token in ["unclaimed", "no gbp", "no listing", "no profile"])


def _normalize_intent_niche(term: str) -> str:
    t = str(term or "").lower()
    if "locksmith" in t:
        return "locksmiths"
    if "plumb" in t:
        return "plumbers"
    if "hvac" in t or "heating" in t or "air" in t:
        return "hvac contractors"
    if "electric" in t:
        return "electricians"
    if "tow" in t:
        return "towing"
    if "garage" in t:
        return "garage door"
    return DEFAULT_TARGET_NICHE


async def _search_intent_directory(term: str, location: str, limit: int = 8) -> list:
    from tools.gbp_audit import search_google_maps, lookup_phone_number

    out = []
    seen = set()
    results = await search_google_maps(term, location, limit=limit)

    for item in results:
        if len(out) >= limit:
            break
        if not isinstance(item, dict) or item.get("error"):
            continue

        name = str(item.get("name", "")).strip()
        if not name or name.lower() in seen:
            continue

        phone = str(item.get("phone", "") or "").strip()
        website = str(item.get("website", "") or "").strip()

        # Many Yelp/Maps results omit phone on listing pages; enrich via search.
        if not phone:
            phone = str(await lookup_phone_number(name, location, website)).strip()

        if not phone:
            continue

        seen.add(name.lower())
        out.append({
            "business_name": name,
            "phone": phone,
            "website": website,
            "location": location,
            "term": term,
            "source": item.get("source", "multi"),
        })

    return out

@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduled_events_runner
    init_db()
    _load_scheduled_events()
    scheduled_events_runner = asyncio.create_task(_scheduled_events_loop())
    asyncio.create_task(_auto_approve_worker())
    log_event("system", "thought", f"Agent team starting up — {len(AGENT_MAP)} agents loading...")
    log_event("system", "thought", f"Katy's brief loaded ({len(KATY_BRIEF)} chars)")
    log_event("system", "thought", f"Auto-approve: reply drafts send in {AUTO_APPROVE_MINUTES} min if not rejected")
    yield
    if scheduled_events_runner:
        scheduled_events_runner.cancel()
    scheduler.stop()

app = FastAPI(title="Katy Agent Team", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/dashboard")
def dashboard():
    # Serve the modern dashboard file only.
    for candidate in [
        Path("/Users/katycat/Downloads/agent_team/orchestrator/dashboard/index.html"),
        Path(__file__).parent.parent / "dashboard" / "index.html",
    ]:
        if candidate.exists():
            return FileResponse(str(candidate), media_type="text/html",
                headers={"Cache-Control": "no-store, no-cache, must-revalidate",
                         "Pragma": "no-cache"})
    return {"error": "Dashboard not found"}

@app.get("/logs")
def get_logs(limit: int = 100):
    """Alias for /events — returns recent agent activity logs."""
    return list(reversed(event_stream))[:limit]


@app.get("/compliance/logs")
def get_compliance_logs(category: str = "all", limit: int = 100):
    safe_limit = max(1, min(int(limit or 100), 500))
    files = [
        COMPLIANCE_LOG_DIR / f"{category}.jsonl"
    ] if category != "all" else sorted(COMPLIANCE_LOG_DIR.glob("*.jsonl"))
    rows = []
    for file_path in files:
        if not file_path.exists():
            continue
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    rows.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    return rows[:safe_limit]


@app.get("/compliance/dnc")
def get_internal_dnc_list(limit: int = 200):
    from memory.memory import get_db
    safe_limit = max(1, min(int(limit or 200), 1000))
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM dnc_entries ORDER BY updated_at DESC LIMIT ?",
        (safe_limit,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/")
def root():
    return {"status": "online", "agents": list(AGENT_MAP.keys()), "total": len(AGENT_MAP)}

@app.get("/events")
def get_events(since_id: int = 0):
    return [e for e in event_stream if e["id"] > since_id]

@app.get("/approvals")
def get_approvals():
    return [a for a in approval_queue if a["status"] == "pending"]

@app.post("/approvals/{approval_id}/approve")
async def approve_action(approval_id: int):
    for item in approval_queue:
        if item["id"] == approval_id and item["status"] == "pending":
            item["status"] = "approved"
            log_event("system", "action", f"Katy approved: {item['action']}")
            # Execute auto-approvable actions immediately on explicit YES
            if item["action"] in _AUTO_APPROVE_ACTIONS:
                await _execute_approval(item)
                return {"status": "approved", "sent": item.get("send_result", {}).get("sent"), "item": item}

            # Auto-send email immediately on approval
            if item.get("action") == "send_email":
                details = item.get("details", {})
                to = details.get("to", "")
                subject = details.get("subject", "")
                body = details.get("body", "")
                prospect_name = details.get("prospect_name", "")
                location = details.get("location", "")

                if to and "@" in to and subject and body:
                    outreach = OutreachAgent(KATY_BRIEF, log_event, request_approval)
                    send_result = await outreach.send_approved_outreach(
                        prospect_name, location, to, subject, body
                    )
                    item["send_result"] = send_result
                    log_event("outreach", "action",
                              f"Auto-sent email to {to}: {send_result.get('sent', False)}")

                    # Also send Facebook DM if page was found
                    from tools.browser import browser_tool
                    if not browser_tool.browser:
                        await browser_tool.start()

                    facebook_url = details.get("facebook_url", "")
                    if facebook_url:
                        try:
                            fb_result = await browser_tool.send_facebook_dm(facebook_url, body)
                            item["facebook_result"] = fb_result
                            log_event("outreach", "action",
                                      f"Facebook DM → {facebook_url}: {fb_result.get('sent', False)}")
                        except Exception as e:
                            log_event("outreach", "thought", f"Facebook DM failed: {e}")

                    # Also send Instagram DM if handle was found
                    instagram_handle = details.get("instagram_handle", "")
                    if instagram_handle:
                        try:
                            ig_result = await browser_tool.send_instagram_dm(instagram_handle, body)
                            item["instagram_result"] = ig_result
                            log_event("outreach", "action",
                                      f"Instagram DM → @{instagram_handle}: {ig_result.get('sent', False)}")
                        except Exception as e:
                            log_event("outreach", "thought", f"Instagram DM failed: {e}")

                    return {"status": "approved", "sent": send_result.get("sent"), "item": item}

            return {"status": "approved", "item": item}
    return {"error": "Not found"}

@app.post("/approvals/{approval_id}/reject")
def reject_action(approval_id: int):
    for item in approval_queue:
        if item["id"] == approval_id:
            item["status"] = "rejected"
            log_event("system", "action", f"Katy rejected: {item['action']}")
            return {"status": "rejected", "item": item}
    return {"error": "Not found"}

def make_task_handler():
    return TaskHandler(AGENT_MAP, KATY_BRIEF, log_event, request_approval)


def make_playbook_runner():
    def runtime_context():
        active_events = [
            _serialize_scheduled_event(item)
            for item in scheduled_events
            if item.get("status") in {"scheduled", "running"}
        ]
        pending_approvals = sum(1 for item in approval_queue if item.get("status") == "pending")
        return {
            "scheduled_events": active_events,
            "pending_approvals": pending_approvals,
        }

    return PlaybookRunner(make_task_handler(), log_event, runtime_context)

@app.post("/chat")
async def chat(body: dict):
    message = body.get("message", "")
    agent_key = (body.get("agent") or "coordinator").strip().lower()
    log_event("katy", "message", message)
    handler = make_task_handler()

    # Route directly to the requested agent when one is explicitly selected.
    # Fall back to Coordinator (which can orchestrate the full team) for
    # "coordinator", "auto", blank, or any unrecognised key.
    if agent_key and agent_key not in ("coordinator", "auto") and agent_key in AGENT_MAP:
        agent = AGENT_MAP[agent_key](KATY_BRIEF, log_event, request_approval)
        response = await agent.handle_message(message)
        log_event(agent_key, "message", response[:400])
    else:
        coordinator = CoordinatorAgent(KATY_BRIEF, log_event, request_approval,
                                       dispatch_fn=handler.dispatch)
        response = await coordinator.handle_message(message)
        log_event("coordinator", "message", response[:400])

    return {"response": response}

@app.post("/task")
async def run_task(body: dict):
    task = body.get("task", "")
    agent_name = body.get("agent", "coordinator")
    try:
        result = await _execute_agent_task(agent_name, task)
        import_stats = await _persist_prospects_from_result(agent_name, result)
        if import_stats.get("parsed", 0) > 0:
            result = (
                f"{result}\n\n"
                f"[pipeline] prospects parsed={import_stats['parsed']} "
                f"saved={import_stats['saved']} "
                f"updated={import_stats['updated']} "
                f"phone_enriched={import_stats['enriched_phone']}"
            )
        return {"result": result}
    except ValueError as e:
        return {"error": str(e)}


@app.get("/playbooks")
async def list_playbooks():
    runner = make_playbook_runner()
    return runner.list_playbooks()


@app.post("/playbooks/{playbook_id}")
async def run_playbook(playbook_id: str, body: dict | None = None):
    runner = make_playbook_runner()
    try:
        return await runner.run(playbook_id, body)
    except ValueError as e:
        return {"error": str(e)}


@app.get("/scheduled-events")
async def list_scheduled_events(include_history: bool = False):
    async with scheduled_events_lock:
        items = [
            _serialize_scheduled_event(item)
            for item in scheduled_events
            if include_history or item.get("status") in {"scheduled", "running"}
        ]
    items.sort(key=lambda x: x.get("run_at", ""))
    return items


@app.post("/scheduled-events")
async def create_scheduled_event(body: dict):
    agent_name = body.get("agent", "coordinator")
    task = str(body.get("task", "")).strip()
    run_at_raw = body.get("run_at")

    if not task:
        return {"error": "task is required"}
    if agent_name != "coordinator" and agent_name not in AGENT_MAP:
        return {"error": f"Unknown agent: {agent_name}"}

    try:
        run_at_dt = _parse_schedule_time(run_at_raw)
    except Exception as e:
        return {"error": f"Invalid run_at: {e}"}

    if run_at_dt <= _now_utc():
        return {"error": "run_at must be in the future"}

    async with scheduled_events_lock:
        next_id = max([item.get("id", 0) for item in scheduled_events] + [0]) + 1
        item = {
            "id": next_id,
            "agent": agent_name,
            "task": task,
            "status": "scheduled",
            "run_at": run_at_dt.isoformat(),
            "created_at": _now_utc().isoformat(),
            "started_at": None,
            "completed_at": None,
            "error": "",
            "result_preview": "",
        }
        scheduled_events.append(item)
        _save_scheduled_events()

    log_event("system", "action", f"Manual schedule created #{next_id} for {agent_name} at {run_at_dt.isoformat()}")
    return {"scheduled": _serialize_scheduled_event(item)}


@app.post("/scheduled-events/{event_id}/cancel")
async def cancel_scheduled_event(event_id: int):
    async with scheduled_events_lock:
        item = next((evt for evt in scheduled_events if evt.get("id") == event_id), None)
        if not item:
            return {"error": "Not found"}
        if item.get("status") != "scheduled":
            return {"error": f"Cannot cancel event in status={item.get('status')}"}
        item["status"] = "cancelled"
        item["completed_at"] = _now_utc().isoformat()
        _save_scheduled_events()

    log_event("system", "action", f"Scheduled trigger #{event_id} cancelled")
    return {"cancelled": _serialize_scheduled_event(item)}

@app.get("/status")
def get_status():
    mem = get_memory_summary()
    return {"online": True, "agents": len(AGENT_MAP), "events_logged": len(event_stream),
            "pending_approvals": len([a for a in approval_queue if a["status"]=="pending"]),
            "scheduled_events": len([s for s in scheduled_events if s.get("status") in {"scheduled", "running"}]),
            "brief_loaded": len(KATY_BRIEF) > 0, "memory": mem}

@app.get("/availability")
def get_availability():
    """Get Katy's current availability for agent transfers."""
    from memory.memory import get_availability
    return get_availability()

@app.post("/availability")
def set_availability(body: dict):
    """Set Katy's availability. Body: {"available_now": true/false, "available_until": "ISO string or null"}"""
    from memory.memory import set_availability
    available_now = body.get("available_now", False)
    available_until = body.get("available_until")
    set_availability(available_now, available_until)
    log_event("system", "action", f"Availability set: available_now={available_now}")
    return {"set": True, "available_now": available_now, "available_until": available_until}

@app.get("/agents")
def list_agents():
    return {"agents": list(AGENT_MAP.keys()), "total": len(AGENT_MAP)}

@app.get("/memory/summary")
def memory_summary():
    return get_memory_summary()

@app.get("/memory/jobs")
def memory_jobs(status: str = None):
    from memory.memory import get_jobs
    return get_jobs(status)

@app.get("/memory/contacts")
def memory_contacts(status: str = None):
    from memory.memory import get_contacts
    return get_contacts(status)

@app.get("/memory/tasks")
def memory_tasks(agent: str = None, limit: int = 20):
    from memory.memory import get_recent_tasks
    return get_recent_tasks(agent, limit)

@app.post("/memory/jobs")
def add_job(body: dict):
    from memory.memory import save_job
    is_new = save_job(title=body.get("title"), company=body.get("company"),
                      url=body.get("url"), salary=body.get("salary"),
                      location=body.get("location"), match_score=body.get("match_score"),
                      notes=body.get("notes"))
    return {"saved": is_new}

@app.put("/memory/jobs/status")
def update_job(body: dict):
    from memory.memory import update_job_status
    update_job_status(body["title"], body["company"], body["status"])
    return {"updated": True}

@app.post("/browser/login/{platform}")
async def browser_login(platform: str):
    from tools.browser import browser_tool
    if not browser_tool.browser:
        await browser_tool.start()
    result = await browser_tool.login_flow(platform)
    return {"result": result}

@app.get("/browser/sessions")
def browser_sessions():
    from pathlib import Path
    session_dir = Path(os.getenv("SESSION_DIR", Path(__file__).parent / "sessions"))
    return {"linkedin": (session_dir/"linkedin_session.json").exists(),
            "facebook": (session_dir/"facebook_session.json").exists()}

@app.get("/prospects")
def get_prospects_list(stage: str = None, priority: str = None, limit: int = 50):
    from memory.memory import get_prospects
    safe_limit = max(1, min(int(limit or 50), 500))
    return get_prospects(stage=stage, priority=priority, limit=safe_limit)


@app.get("/prospects/call-list")
def get_call_list(count: int = 20, priority: str = None):
    """Return a deterministic, call-ready list of prospects with phone numbers."""
    from memory.memory import get_prospects

    safe_count = max(1, min(int(count or 20), 200))
    all_rows = get_prospects(priority=priority, limit=500)
    rows = [
        p for p in all_rows
        if str(p.get("phone", "")).strip()
        and not _is_legacy_profile_opportunity(p)
        and not _dnc_scrub(p.get("phone", ""), p.get("business_name", ""), p)[0]
    ]

    priority_order = {"HOT": 0, "WARM": 1, "COLD": 2}
    rows.sort(key=lambda p: (
        -_intent_score(p),
        priority_order.get(str(p.get("priority", "WARM")).upper(), 9),
    ))

    return {
        "count": min(safe_count, len(rows)),
        "total_with_phone": len(rows),
        "items": rows[:safe_count],
    }


@app.post("/prospects/discover-intent")
async def discover_intent_prospects(body: dict | None = None):
    """Discover and save callable prospects that likely have answering-service buyer intent."""
    from memory.memory import save_prospect, get_prospects

    payload = body or {}
    queries = payload.get("queries") or [
        {"term": "24 hour locksmith", "location": "Houston TX"},
        {"term": "emergency plumber", "location": "Dallas TX"},
        {"term": "after hours electrician", "location": "San Antonio TX"},
        {"term": "weekend plumber", "location": "Phoenix AZ"},
        {"term": "urgent locksmith", "location": "Columbus OH"},
    ]
    per_query = max(1, min(int(payload.get("per_query", 8)), 20))

    saved = 0
    scanned = 0
    rejected = 0
    source_errors = []
    for q in queries:
        term = str(q.get("term", "")).strip()
        location = str(q.get("location", "")).strip()
        if not term or not location:
            continue
        try:
            matches = await _search_intent_directory(term, location, per_query)
        except Exception as e:
            source_errors.append({"term": term, "location": location, "error": str(e)})
            continue
        for m in matches:
            scanned += 1
            niche = _normalize_intent_niche(term)
            is_new = save_prospect(
                business_name=m["business_name"],
                location=location,
                niche=niche,
                phone=m["phone"],
                website=m.get("website", ""),
                priority="HOT",
                pipeline_stage="found",
                gbp_score=3.0,
                research_notes=(
                    f"Buyer-intent signal: found under '{term}' in {location}. "
                    "Likely high inbound call urgency and after-hours demand."
                ),
                notes="intent: emergency_or_24h_search",
            )
            if is_new:
                saved += 1
            else:
                rejected += 1

    current = get_prospects(priority="HOT", limit=500)
    current = [p for p in current if str(p.get("phone", "")).strip() and not _is_legacy_profile_opportunity(p)]
    current.sort(key=lambda p: (-_intent_score(p), str(p.get("business_name", ""))))
    return {
        "queries": len(queries),
        "scanned": scanned,
        "saved": saved,
        "rejected": rejected,
        "callable_now": len(current),
        "source_errors": source_errors[:10],
        "items": current[:20],
    }

@app.post("/prospects")
def create_prospect(body: dict):
    """Add a new prospect manually."""
    from memory.memory import save_prospect
    business_name = body.get("business_name", "").strip()
    location = body.get("location", "").strip()
    
    if not business_name or not location:
        return {"created": False, "reason": "business_name and location are required"}
    
    # Extract allowed fields
    allowed_fields = {
        "phone", "email", "website", "owner_name", "niche", "priority", 
        "pipeline_stage", "research_notes", "notes", "gbp_score",
        "dnc_status", "dnc_checked_at", "dnc_source", "opt_out_at", "opt_out_reason",
        "ai_call_written_consent", "ai_call_express_consent", "ai_call_consent_source",
        "ai_call_consent_notes", "ai_call_consent_updated_at"
    }
    kwargs = {k: v for k, v in body.items() if k in allowed_fields and v is not None}
    
    # Set defaults if not provided
    if "niche" not in kwargs:
        kwargs["niche"] = "general_service"
    if "priority" not in kwargs:
        kwargs["priority"] = "WARM"
    if "pipeline_stage" not in kwargs:
        kwargs["pipeline_stage"] = "manual_entry"
    
    is_new = save_prospect(business_name, location, **kwargs)
    
    if not is_new:
        return {"created": False, "reason": "prospect already exists or failed niche validation"}
    
    log_event("system", "action", f"New prospect added manually: {business_name}, {location}")
    
    # Fetch and return the newly created prospect
    from memory.memory import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM prospects WHERE business_name=? AND location=? ORDER BY id DESC LIMIT 1",
        (business_name, location)
    ).fetchone()
    conn.close()
    
    if row:
        prospect = dict(row)
        return {"created": True, "prospect": prospect}
    
    return {"created": True, "prospect": None}


@app.post("/prospects/import-from-sheets")
async def import_prospects_from_sheets(body: dict | None = None):
    from memory.memory import save_prospect, update_prospect

    payload = body or {}
    expected_token = str(os.getenv("GOOGLE_SHEETS_IMPORT_TOKEN", os.getenv("GOOGLE_SHEETS_WEBAPP_TOKEN", ""))).strip()
    provided_token = str(payload.get("token") or "").strip()
    if expected_token and provided_token != expected_token:
        return {"ok": False, "reason": "invalid token"}

    rows = payload.get("rows") or payload.get("prospects") or []
    if isinstance(rows, dict):
        rows = [rows]

    normalized = _normalize_sheet_import_rows(rows)
    if not normalized:
        return {"ok": False, "reason": "no valid rows", "received": len(rows) if isinstance(rows, list) else 0}

    saved = 0
    updated = 0
    imported_rows = []
    for item in normalized:
        fields = {k: v for k, v in item.items() if k not in {"business_name", "location"}}
        is_new = save_prospect(item["business_name"], item["location"], **fields)
        if is_new:
            saved += 1
        else:
            update_prospect(item["business_name"], item["location"], **fields)
            updated += 1
        imported_rows.append(item)

    deep_dive = bool(payload.get("deep_dive"))
    deep_dive_limit = payload.get("deep_dive_limit", 5)
    try:
        deep_dive_limit = int(deep_dive_limit)
    except (TypeError, ValueError):
        deep_dive_limit = 5

    deep_dive_stats = {"deep_dived": 0, "enriched_phone": 0}
    if deep_dive:
        deep_dive_stats = await _deep_dive_prospect_rows(imported_rows, limit=deep_dive_limit)

    log_event(
        "system",
        "action",
        f"Sheet import: received={len(rows)} parsed={len(normalized)} saved={saved} updated={updated} deep_dived={deep_dive_stats['deep_dived']}",
    )
    return {
        "ok": True,
        "received": len(rows),
        "parsed": len(normalized),
        "saved": saved,
        "updated": updated,
        **deep_dive_stats,
    }

@app.patch("/prospects/{prospect_id}")
def patch_prospect(prospect_id: int, body: dict):
    """Update any fields on a prospect by ID."""
    from memory.memory import get_db
    allowed = {"owner_name","phone","email","website","priority","pipeline_stage",
               "research_notes","notes","niche","outreach_draft","dnc_status",
               "dnc_checked_at","dnc_source","opt_out_at","opt_out_reason",
               "ai_call_written_consent","ai_call_express_consent","ai_call_consent_source",
               "ai_call_consent_notes","ai_call_consent_updated_at"}
    updates = {k:v for k,v in body.items() if k in allowed and v is not None}
    if not updates:
        return {"updated": False, "reason": "no valid fields"}
    conn = get_db()
    existing = conn.execute("SELECT * FROM prospects WHERE id=?", (prospect_id,)).fetchone()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    set_clause += ", updated_at=datetime('now')"
    conn.execute(f"UPDATE prospects SET {set_clause} WHERE id=?",
                 list(updates.values()) + [prospect_id])
    conn.commit()
    conn.close()
    if existing:
        existing_dict = dict(existing)
        if updates.get("dnc_status") in {"internal_opt_out", "dnc", "revoked", "blocked"} or updates.get("opt_out_at"):
            _record_dnc_entry(
                existing_dict.get("phone", ""),
                existing_dict.get("business_name", ""),
                updates.get("opt_out_reason") or updates.get("dnc_status") or "manual_update",
                source=updates.get("dnc_source") or "manual_update",
                notes=updates.get("ai_call_consent_notes") or "",
            )
        if any(key in updates for key in {"ai_call_written_consent", "ai_call_express_consent", "ai_call_consent_source", "ai_call_consent_notes"}):
            log_compliance_event("consent", "updated", {
                "prospect_id": prospect_id,
                "business_name": existing_dict.get("business_name", ""),
                "phone": _normalize_phone(existing_dict.get("phone", "")),
                "updates": updates,
            })
    log_event("system", "action", f"Prospect {prospect_id} updated: {list(updates.keys())}")
    return {"updated": True, "id": prospect_id, "fields": list(updates.keys())}

@app.delete("/prospects/{prospect_id}")
def delete_prospect(prospect_id: int):
    from memory.memory import get_db
    conn = get_db()
    conn.execute("DELETE FROM prospects WHERE id=?", (prospect_id,))
    conn.commit()
    conn.close()
    log_event("system", "action", f"Prospect {prospect_id} deleted")
    return {"deleted": True, "id": prospect_id}


@app.post("/prospects/fill-phones")
async def fill_missing_phones():
    """Find phone numbers for all prospects that have none."""
    from memory.memory import get_prospects, update_prospect, get_db
    from tools.gbp_audit import lookup_phone_number
    prospects = get_prospects()
    missing = [p for p in prospects if not p.get("phone")]
    log_event("system", "action", f"Phone lookup: filling {len(missing)} prospects with no phone")
    filled = 0
    for p in missing:
        phone = await lookup_phone_number(
            p.get("business_name", ""),
            p.get("location", ""),
            website=p.get("website", "")
        )
        if phone:
            update_prospect(p["business_name"], p["location"], phone=phone)
            filled += 1
            log_event("system", "action", f"📞 Found phone for {p['business_name']}: {phone}")
    return {"checked": len(missing), "filled": filled}


@app.get("/prospects/sheets-sync-status")
def prospect_sheets_sync_status():
    from tools.sheets_tool import sheets_sync_config_status
    return sheets_sync_config_status()


@app.post("/prospects/sheets-sync-test")
def prospect_sheets_sync_test(body: dict | None = None):
    from tools.sheets_tool import push_prospect_sync
    payload = body or {}
    sample = {
        "business_name": payload.get("business_name") or "SYNC TEST - Katy Pipeline",
        "phone": payload.get("phone") or "",
        "location": payload.get("location") or "Charleston WV",
        "niche": payload.get("niche") or DEFAULT_TARGET_NICHE,
        "gbp_score": payload.get("gbp_score") or 3.0,
        "priority": payload.get("priority") or "WARM",
        "gbp_issues": payload.get("gbp_issues") or ["sync_test"],
        "website": payload.get("website") or "",
        "maps_url": payload.get("maps_url") or "",
        "notes": payload.get("notes") or "manual sheets sync test",
    }
    ok = push_prospect_sync(sample)
    return {"ok": ok, "sample": sample}


@app.post("/execute")
async def execute_mission(body: dict):
    """Run multiple agents in sequence with output chaining (Swarm-style handoff)."""
    mission = body.get("mission", "")
    agents_to_run = body.get("agents", ["lead_gen", "small_biz_expert", "outreach"])
    parallel = body.get("parallel", False)

    log_event("task_handler", "action", f"Mission start: {mission[:80]}")
    handler = make_task_handler()

    if parallel:
        results = await handler.dispatch_parallel(agents_to_run, mission)
    else:
        results = await handler.dispatch(agents_to_run, mission)

    return {"results": results, "mission": mission}

# ─── VAPI ENDPOINTS ───────────────────────────────────────────────────────────

@app.get("/vapi/status")
async def vapi_status():
    """Check VAPI configuration and account."""
    from tools.vapi_tool import is_configured, list_phone_numbers
    if not is_configured():
        return {"configured": False, "error": "VAPI_API_KEY not set"}
    try:
        numbers = await list_phone_numbers()
        return {"configured": True, "phone_numbers": numbers}
    except Exception as e:
        return {"configured": True, "error": str(e)}


@app.post("/vapi/call")
async def trigger_vapi_call(body: dict):
    """
    Trigger an outbound AI sales call to a prospect.
    Body: {
        "prospect_phone": "...",
        "prospect_name": "...",
        "business_name": "...",
        "gbp_condition": "NO_PROFILE|INCOMPLETE_PROFILE|OUTDATED_PROFILE|INCORRECT_PROFILE",
        "issues": ["missing hours", "no photos", ...],
        "assistant_id": "...",
        "phone_number_id": "..."
    }
    """
    from tools.vapi_tool import make_call
    from memory.memory import get_prospects

    if not _eric_calling_enabled():
        log_event("vapi", "warn", "Blocked outbound call: ENABLE_ERIC_CALLS is false")
        return {
            "blocked": True,
            "reason": "Outbound calling is disabled. Set ENABLE_ERIC_CALLS=true only after manual phone verification.",
        }

    # Auto-fill from prospect database if phone matches
    prospect_phone = body.get("prospect_phone", "")
    all_prospects = get_prospects(limit=500)
    prospect_data = _find_matching_prospect(prospect_phone, all_prospects)
    call_spec = _build_vapi_call_spec(body, prospect_data)
    blocked, reason = _dnc_scrub(call_spec.get("prospect_phone", ""), call_spec.get("business_name", ""), prospect_data)
    if blocked:
        log_event("vapi", "warn", f"Blocked outbound call to {call_spec.get('business_name') or prospect_phone}: {reason}")
        log_compliance_event("call_screening", "blocked", {
            "business_name": call_spec.get("business_name", ""),
            "prospect_phone": _normalize_phone(call_spec.get("prospect_phone", "")),
            "reason": reason,
            "mode": "single_call",
        })
        return {"blocked": True, "reason": f"DNC scrub blocked this call: {reason}"}

    result = await make_call(**call_spec)
    business_name = call_spec.get("business_name") or body.get("business_name") or "unknown prospect"
    log_event("vapi", "action", f"Call triggered to {business_name} — {result.get('id', 'error')}")
    log_compliance_event("call_screening", "passed", {
        "business_name": business_name,
        "prospect_phone": _normalize_phone(call_spec.get("prospect_phone", "")),
        "mode": "single_call",
    })
    return result


@app.post("/vapi/call-list")
async def trigger_vapi_call_list(body: dict):
    """
    Trigger outbound AI sales calls for a list of prospects or a filtered DB slice.
    Body supports either:
    - {"prospects": [{...}], "limit": 10}
    - {"stage": "researched", "priority": "HOT", "limit": 10, "business_names": ["..."]}
    """
    from tools.vapi_tool import make_calls_batch, is_configured
    from memory.memory import get_prospects, update_prospect

    if not _eric_calling_enabled():
        log_event("vapi", "warn", "Blocked batch outbound calls: ENABLE_ERIC_CALLS is false")
        return {
            "queued": 0,
            "failed": 0,
            "results": [],
            "blocked": True,
            "error": "Outbound calling is disabled. Set ENABLE_ERIC_CALLS=true only after manual phone verification.",
        }

    if not is_configured():
        return {"queued": 0, "results": [], "error": "VAPI_API_KEY not set"}

    requested_limit = body.get("limit", 10)
    try:
        limit = max(1, min(int(requested_limit), 50))
    except (TypeError, ValueError):
        limit = 10

    delay_seconds = body.get("delay_seconds", 0)
    try:
        delay_seconds = max(0.0, float(delay_seconds))
    except (TypeError, ValueError):
        delay_seconds = 0.0

    business_names = {name for name in (body.get("business_names") or []) if name}
    success_stage = body.get("success_stage", "calling")
    only_uncalled = body.get("only_uncalled", True)
    uncalled_stages = {"calling", "callback_scheduled", "completed", "do_not_call", "won", "lost"}

    include_keywords = {str(k).strip().lower() for k in (body.get("include_niches") or body.get("include_keywords") or []) if str(k).strip()}
    exclude_keywords = {str(k).strip().lower() for k in (body.get("exclude_niches") or body.get("exclude_keywords") or []) if str(k).strip()}

    if body.get("owner_answered_only", False):
        include_keywords.update({
            "hvac", "heating", "air conditioning", "locksmith", "carpenter",
            "renovation", "remodel", "contractor", "plumber", "electrician",
            "handyman", "roofing", "roofer", "painting", "landscaping",
        })

    if body.get("exclude_dentists", True):
        exclude_keywords.update({"dentist", "dental", "orthodont", "oral surgery"})

    source_prospects = body.get("prospects") or get_prospects(
        stage=body.get("stage"),
        priority=body.get("priority"),
        limit=max(limit * 3, 50),
    )

    call_specs = []
    matched_db_records = []
    skipped = []

    db_prospects = get_prospects(limit=500)
    for prospect in source_prospects:
        business_name = prospect.get("business_name", "")
        pipeline_stage = prospect.get("pipeline_stage", "")
        text_blob = _prospect_text_blob(prospect)
        niche = prospect.get("niche", "")
        score = _prospect_score(prospect)

        if business_names and business_name not in business_names:
            continue
        if not _is_allowed_niche(niche):
            skipped.append({"business_name": business_name, "reason": f"blocked niche={niche}"})
            continue
        if score > MAX_PROSPECT_SCORE:
            skipped.append({"business_name": business_name, "reason": f"score={score} above {MAX_PROSPECT_SCORE}"})
            continue
        if include_keywords and not _keyword_match(text_blob, include_keywords):
            skipped.append({"business_name": business_name, "reason": "outside target niches"})
            continue
        if exclude_keywords and _keyword_match(text_blob, exclude_keywords):
            skipped.append({"business_name": business_name, "reason": "excluded niche"})
            continue
        if only_uncalled and pipeline_stage in uncalled_stages:
            skipped.append({"business_name": business_name, "reason": f"stage={pipeline_stage}"})
            continue
        if not _normalize_phone(prospect.get("phone", "")):
            skipped.append({"business_name": business_name, "reason": "missing phone"})
            continue
        blocked, reason = _dnc_scrub(prospect.get("phone", ""), business_name, prospect)
        if blocked:
            skipped.append({"business_name": business_name, "reason": f"dnc_blocked:{reason}"})
            log_compliance_event("call_screening", "blocked", {
                "business_name": business_name,
                "prospect_phone": _normalize_phone(prospect.get("phone", "")),
                "reason": reason,
                "mode": "batch_call",
            })
            continue

        call_specs.append(_build_vapi_call_spec({}, prospect))
        matched_db_records.append(_find_matching_prospect(prospect.get("phone", ""), db_prospects) or prospect)
        if len(call_specs) >= limit:
            break

    if not call_specs:
        return {"queued": 0, "results": [], "skipped": skipped, "error": "No callable prospects found"}

    results = await make_calls_batch(call_specs, delay_seconds=delay_seconds)

    response_rows = []
    queued = 0
    failed = 0
    for call_result, db_record in zip(results, matched_db_records):
        response = call_result.get("response", {})
        business_name = call_result.get("request", {}).get("business_name", "")
        success = bool(response.get("id"))
        if success:
            queued += 1
            if db_record.get("business_name") and db_record.get("location"):
                update_prospect(
                    business_name=db_record["business_name"],
                    location=db_record.get("location", ""),
                    pipeline_stage=success_stage,
                )
        else:
            failed += 1

        response_rows.append({
            "business_name": business_name,
            "prospect_phone": call_result.get("request", {}).get("prospect_phone", ""),
            "status": "queued" if success else "error",
            "call_id": response.get("id", ""),
            "error": response.get("error", ""),
        })

    log_event("vapi", "action", f"Batch call push complete — queued {queued}, failed {failed}")
    return {
        "queued": queued,
        "failed": failed,
        "results": response_rows,
        "skipped": skipped,
    }


@app.post("/prospects/cleanup-targeting")
def cleanup_targeting(body: dict = None):
    """Delete legacy prospects outside allowed niches or above max score."""
    from memory.memory import cleanup_prospects_by_policy

    body = body or {}
    dry_run = bool(body.get("dry_run", True))
    result = cleanup_prospects_by_policy(dry_run=dry_run)

    action = "dry-run" if dry_run else "deleted"
    log_event(
        "system",
        "action",
        f"Prospect cleanup {action}: {result.get('violations_found', 0)} violations",
    )
    return result


@app.post("/vapi/get-prospect")
async def vapi_get_prospect(body: dict):
    """
    Webhook called by VAPI during a call to get prospect details.
    Returns the specific GBP issues so the AI can personalize the pitch.
    """
    phone = body.get("message", {}).get("functionCall", {}).get("parameters", {}).get("phone", "")
    from memory.memory import get_prospects
    prospects = get_prospects()
    match = next((p for p in prospects if _phones_match(p.get("phone", ""), phone)), None)
    if match:
        issues = _parse_gbp_issues(match.get("gbp_issues", "[]"))
        return {
            "result": json.dumps({
                "business_name": match.get("business_name") or "",
                "owner_name": match.get("owner_name") or "business owner",
                "city": match.get("location", ""),
                "business_type": match.get("niche", "business"),
                "gbp_condition": _infer_gbp_condition(issues),
                "issues": issues,
                "missing_items": ", ".join(issues[:3]),
            })
        }

    # No local DB match — check Google Sheet in real time
    lookup_url = os.getenv("BUSINESS_LOOKUP_URL", "")
    if lookup_url and phone:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(lookup_url, params={"phone": phone}, timeout=8)
                if resp.status_code == 200:
                    sheet_data = resp.json()
                    if sheet_data and sheet_data.get("found") is not False:
                        return {
                            "result": json.dumps({
                                "business_name": sheet_data.get("business_name", ""),
                                "owner_name": sheet_data.get("owner_name") or sheet_data.get("contact_name") or "there",
                                "city": sheet_data.get("city", ""),
                                "business_type": sheet_data.get("niche") or sheet_data.get("business_type", ""),
                                "source": "google_sheet",
                            })
                        }
        except Exception as e:
            log_event("vapi", "warn", f"get-prospect: Sheet lookup failed: {e}")

    log_event("vapi", "warn", f"get-prospect: no match for phone {phone!r}")
    return {"result": json.dumps({"owner_name": "there", "business_name": "", "prospect_not_found": True})}


async def _web_search_business(business_name: str, city: str = "") -> dict:
    """
    Fast httpx-only web lookup for a specific business.
    Searches Google for the business and parses the knowledge panel snippet.
    Targets: address, hours, website, services, rating. No Playwright — must complete < 3s.
    """
    import httpx, re

    query = f"{business_name} {city}".strip()
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}&hl=en"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    data = {}
    try:
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=5) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return data
            html = resp.text

        # Address — appears in knowledge panel as plain text near maps
        addr_m = re.search(r'(\d+\s+[A-Z][^,<]{3,40},\s*[A-Z][^<]{2,30},\s*[A-Z]{2}\s*\d{5})', html)
        if addr_m:
            data["address"] = addr_m.group(1).strip()

        # Phone — US format
        phone_m = re.search(r'\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}', html)
        if phone_m:
            data["phone_web"] = phone_m.group(0).strip()

        # Website — look for a "Visit website" type link in the panel
        web_m = re.search(r'href="(https?://(?!(?:www\.google|maps\.google|support\.google|accounts\.google))[^"]{8,80})"[^>]*>[^<]*(?:website|site|visit)', html, re.IGNORECASE)
        if web_m:
            data["website"] = web_m.group(1).strip()

        # Rating
        rating_m = re.search(r'(\d\.\d)\s*(?:stars?|★|out of 5|\()', html)
        if rating_m:
            data["rating"] = rating_m.group(1)

        # Review count
        rev_m = re.search(r'([\d,]+)\s+(?:Google\s+)?reviews?', html, re.IGNORECASE)
        if rev_m:
            data["review_count"] = rev_m.group(1).replace(",", "")

        # Hours — look for "Open" / "Closed" signals with time patterns
        hours_m = re.search(r'(?:Opens?|Closes?|Open until|Closed)\s+[·•]?\s*(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm))', html)
        if hours_m:
            data["hours_signal"] = hours_m.group(0).strip()

        # Category/type — often appears near the business name in the panel
        cat_m = re.search(r'"LocalBusiness"[^}]*"description"\s*:\s*"([^"]{10,120})"', html)
        if not cat_m:
            cat_m = re.search(r'data-attrid="description"[^>]*>([^<]{20,200})<', html)
        if cat_m:
            data["description"] = cat_m.group(1).strip()

    except Exception as e:
        pass  # Web lookup is best-effort — never block the call

    return data


@app.post("/vapi/lookup-business")
async def vapi_lookup_business(body: dict):
    """
    Called by Eric in real-time when a prospect mentions their business name on an inbound call.
    Priority order: Google Sheet > local DB > fast web search (httpx only, no Playwright).
    Returns merged intel so Eric can personalize the conversation immediately.
    """
    params = body.get("message", {}).get("functionCall", {}).get("parameters", body)
    business_name = params.get("business_name", "").strip()
    phone = params.get("phone", "").strip()

    result = {}

    # 0. HubSpot CRM lookup
    hubspot_token = os.getenv('HUBSPOT_ACCESS_TOKEN') or os.getenv('HUBSPOT_API_KEY')
    if hubspot_token and (phone or business_name):
        try:
            import httpx as _hx
            _val = (phone or '').replace('+1','').replace('-','').replace('(','').replace(')','').replace(' ','') if phone else business_name
            _hs_body = {'query':_val,'properties':['firstname','lastname','company','phone','email','city','state','jobtitle','industry','hs_lead_status']}
            async with _hx.AsyncClient() as _c:
                _r = await _c.post('https://api.hubapi.com/crm/v3/objects/contacts/search',json=_hs_body,headers={'Authorization':f'Bearer {hubspot_token}'},timeout=5)
                if _r.status_code == 200:
                    _d = _r.json()
                    if _d.get('total',0) > 0:
                        _p = _d['results'][0]['properties']
                        result = {'owner_name':f"{_p.get('firstname','')} {_p.get('lastname','')}".strip(),'business_name':_p.get('company',''),'city':_p.get('city',''),'business_type':_p.get('industry',''),'email':_p.get('email',''),'phone':_p.get('phone',''),'crm_status':_p.get('hs_lead_status',''),'source':'hubspot_crm','found':True}
        except Exception as _e:
            log_event('vapi','warn',f'HubSpot lookup failed: {_e}')

    # 1. Local prospects DB
    from memory.memory import get_prospects
    prospects = get_prospects()
    match = None
    if phone:
        match = next((p for p in prospects if _phones_match(p.get("phone", ""), phone)), None)
    if not match and business_name:
        name_lower = business_name.lower()
        match = next((p for p in prospects if name_lower in str(p.get("business_name", "")).lower()), None)

    if match:
        issues = _parse_gbp_issues(match.get("gbp_issues", "[]"))
        result = {
            "business_name": match.get("business_name", ""),
            "owner_name": match.get("owner_name", ""),
            "city": match.get("location", ""),
            "business_type": match.get("niche", ""),
            "services": match.get("services", ""),
            "website": match.get("website", ""),
            "address": match.get("address", ""),
            "hours": match.get("hours", ""),
            "rating": match.get("rating", ""),
            "review_count": match.get("review_count", ""),
            "known_issues": issues[:3],
            "source": "local_db",
        }

    # 2. Google Sheet (Apps Script web app) — wins over DB for any field it has
    lookup_url = os.getenv("BUSINESS_LOOKUP_URL", "")
    if lookup_url and (business_name or phone):
        try:
            import httpx
            qs = {}
            if business_name:
                qs["name"] = business_name
            if phone:
                qs["phone"] = phone
            async with httpx.AsyncClient() as client:
                resp = await client.get(lookup_url, params=qs, timeout=8)
                if resp.status_code == 200:
                    sheet_data = resp.json()
                    if sheet_data and sheet_data.get("found") is not False:
                        result.update({k: v for k, v in sheet_data.items() if v})
                        result["source"] = "google_sheet"
        except Exception as e:
            log_event("vapi", "warn", f"lookup-business: Sheet lookup failed: {e}")

    # 3. Fast web search to fill any remaining gaps (address, hours, website, rating)
    missing_fields = not all([result.get("address"), result.get("website"), result.get("hours")])
    if business_name and missing_fields:
        try:
            web_data = await _web_search_business(business_name, result.get("city", ""))
            # Only fill in gaps — don't overwrite what sheet/DB already has
            for k, v in web_data.items():
                if v and not result.get(k):
                    result[k] = v
            if web_data and "source" not in result:
                result["source"] = "web_search"
        except Exception as e:
            log_event("vapi", "warn", f"lookup-business: Web search failed: {e}")

    if not result:
        log_event("vapi", "warn", f"lookup-business: no data found for name={business_name!r} phone={phone!r}")
        return {"result": json.dumps({"found": False, "business_name": business_name})}

    result["found"] = True
    return {"result": json.dumps(result)}


@app.post("/vapi/schedule-callback")
async def vapi_schedule_callback(body: dict):
    """Eric calls this when a prospect asks for a callback."""
    try:
        params = body.get("message", {}).get("functionCall", {}).get("parameters", body)
        callback_time = params.get("callback_time", "")
        prospect_phone = params.get("prospect_phone", "")
        prospect_email = params.get("prospect_email", "")
        contact_name = params.get("contact_name", "")
        business_name = params.get("business_name", "")
        reason = params.get("reason", "")
        duration_minutes = int(params.get("duration_minutes", 20) or 20)

        from memory.memory import get_prospects, update_prospect
        prospects = get_prospects()
        clean = prospect_phone.replace("+1","").replace("-","").replace(" ","")
        match = next((p for p in prospects if clean in str(p.get("phone","")).replace("-","").replace(" ","")), None)

        if match:
            notes_text = f"Callback requested: {callback_time}" + (f" — {reason}" if reason else "")
            update_prospect(
                business_name=match["business_name"],
                location=match.get("location",""),
                pipeline_stage="callback_scheduled",
                last_call_outcome="busy" if "busy" in str(reason).lower() else "callback_scheduled",
                next_action="schedule_callback",
                callback_due_at=callback_time,
                callback_reason=reason or "callback_requested",
                callback_status="scheduled",
                call_result_summary=notes_text,
                notes=notes_text,
            )

        calendar_created = False
        calendar_link = ""
        calendar_error = ""
        try:
            schedule_dt = _parse_schedule_time(callback_time)
            from tools.google_calendar_tool import create_event
            cal_res = create_event(
                summary=f"Katy Follow-up: {business_name or 'Prospect'}",
                start_at=schedule_dt,
                duration_minutes=duration_minutes,
                description=(
                    f"Callback scheduled by Eric.\n"
                    f"Business: {business_name}\n"
                    f"Phone: {prospect_phone}\n"
                    f"Reason: {reason or 'general follow-up'}"
                ),
                attendee_email=prospect_email,
            )
            calendar_created = bool(cal_res.get("created"))
            calendar_link = cal_res.get("html_link", "")
            calendar_error = cal_res.get("error", "")
        except Exception as e:
            calendar_error = str(e)

        # Send Calendly booking link via SMS if configured
        calendly_link = os.getenv("CALENDLY_LINK", "")
        sms_sent = False
        if calendly_link and prospect_phone:
            try:
                from tools.sms_tool import send_sms
                clean_phone = prospect_phone if prospect_phone.startswith("+") else f"+1{prospect_phone.replace('-','').replace(' ','').replace('(','').replace(')','')[-10:]}"
                sms_body = (
                    f"Hi{(' ' + (match['contact_name'] if match and match.get('contact_name') else '')) if (match and match.get('contact_name')) else ''}, "
                    f"this is Eric from Katy's team. Use this link to pick a time that works for your follow-up call: {calendly_link}"
                )
                res = send_sms(to_number=clean_phone, body=sms_body)
                sms_sent = bool(res.get("sent"))
            except Exception:
                pass

        if calendar_created and match:
            try:
                update_prospect(
                    business_name=match["business_name"],
                    location=match.get("location", ""),
                    notes=json.dumps({
                        "callback_time": callback_time,
                        "calendar_event": calendar_link,
                        "prospect_email": prospect_email,
                        "contact_name": contact_name,
                    }),
                )
            except Exception:
                pass

        log_event(
            "vapi",
            "action",
            f"Callback scheduled: {business_name} — {callback_time}"
            + (" + booking link sent" if sms_sent else "")
            + (" + calendar event created" if calendar_created else (f" + calendar skipped ({calendar_error})" if calendar_error else "")),
        )
        suffix_parts = []
        if calendar_created:
            suffix_parts.append("I also put it on Katy's calendar")
        if sms_sent:
            suffix_parts.append("and texted a booking link so they can self-schedule")
        suffix = (" " + "; ".join(suffix_parts) + ".") if suffix_parts else " I'll make sure Katy follows up then."
        return {"result": f"Callback scheduled for {callback_time}.{suffix}"}
    except Exception as e:
        return {"result": f"Callback noted. ({e})"}


@app.post("/vapi/send-demo-link")
async def vapi_send_demo_link(body: dict):
    """Eric calls this to send the demo and pricing page to a prospect by SMS or email."""
    try:
        params = body.get("message", {}).get("functionCall", {}).get("parameters", body)
        business_name = params.get("business_name", "")
        contact_name = params.get("contact_name", "")
        prospect_phone = params.get("prospect_phone", "")
        prospect_email = params.get("prospect_email", "")
        delivery_method = str(params.get("delivery_method", "sms")).strip().lower()

        demo_url = os.getenv("DEMO_URL", "") or os.getenv("ORCHESTRATOR_URL", "").rstrip("/") + "/demo"

        greeting = f"Hi{(' ' + contact_name) if contact_name else ''}"
        message = (
            f"{greeting}, here is a quick look at how the missed-call answering service works "
            f"and all three pricing tiers so you can review at your own pace: {demo_url}"
        )

        sent_ok = False
        delivery_note = ""

        if delivery_method == "email":
            if not prospect_email:
                return {"result": "I can send it by email, but I still need your best email address."}
            from tools.gmail_tool import send_email
            res = send_email(
                to=prospect_email,
                subject="See How the Missed-Call Answering Service Works",
                body=message,
                from_name="Katy Team",
            )
            sent_ok = bool(res.get("sent"))
            delivery_note = "email"
        else:
            if not prospect_phone:
                return {"result": "I can send it by text, but I still need your best mobile number."}
            from tools.sms_tool import send_sms
            res = send_sms(to_number=prospect_phone, body=message)
            sent_ok = bool(res.get("sent"))
            delivery_note = "sms"

        # Update prospect pipeline stage
        from memory.memory import get_prospects, update_prospect
        prospects = get_prospects()
        clean = prospect_phone.replace("+1", "").replace("-", "").replace(" ", "")
        match = next((p for p in prospects if clean and clean in str(p.get("phone", "")).replace("-", "").replace(" ", "")), None)
        if match:
            update_prospect(
                business_name=match["business_name"],
                location=match.get("location", ""),
                pipeline_stage="demo_sent",
                last_call_outcome="qualified",
                next_action="await_demo_review",
                call_result_summary=f"Demo link sent via {delivery_note}",
                notes=json.dumps({"demo_link_sent": demo_url, "delivery_method": delivery_note}),
            )

        log_event("vapi", "action", f"Demo link sent via {delivery_note}: {business_name or prospect_phone}")
        if sent_ok:
            return {"result": f"Done. I just texted them the demo link. They can review the tiers and pay whenever they are ready."}
        return {"result": "I generated the demo link but delivery failed. Want me to retry?"}
    except Exception as e:
        log_event("vapi", "thought", f"send-demo-link error: {e}")
        return {"result": "I hit a technical issue sending the demo link. Please try again in a moment."}


@app.post("/vapi/send-business-details")
async def vapi_send_business_details(body: dict):
    """Eric sends detailed written follow-up by SMS or email during the call."""
    try:
        params = body.get("message", {}).get("functionCall", {}).get("parameters", body)
        business_name = params.get("business_name", "")
        contact_name = params.get("contact_name", "")
        prospect_phone = params.get("prospect_phone", "")
        prospect_email = params.get("prospect_email", "")
        delivery_method = str(params.get("delivery_method", "sms")).strip().lower()
        details = str(params.get("details", "")).strip()

        if not details:
            return {"result": "I can send details now, but I still need what summary to send."}

        greeting = f"Hi{(' ' + contact_name) if contact_name else ''},"
        pricing_block = (
            "\n\n3 options:\n"
            "⚡ Starter — $500 setup + $97/mo\n"
            "   Best for: solo operators, basic call coverage\n"
            "   Includes: missed-call text back, simple call summaries, business-hours answering\n\n"
            "📞 Standard — $1,000 setup + $197/mo\n"
            "   Best for: small crews, lead qualify + SMS follow-up\n"
            "   Includes: CRM updates, appointment handling, structured lead qualification\n\n"
            "🚀 Pro — $2,000 setup + $297/mo\n"
            "   Best for: busy shops, full automation + booking\n"
            "   Includes: brand-voice delivery, advanced qualification, escalation to owner, priority support\n\n"
            "No contracts. Setup takes about a week."
        )
        message = (
            f"{greeting} Here's a quick recap for {business_name or 'your business'}:\n\n"
            f"Katy's AI answering service picks up every missed call instantly — qualifies the lead, routes next steps, makes sure no job walks away.\n\n"
            f"{details}{pricing_block}\n\n"
            "Want the demo? Reply YES and I'll send it now.\n"
            "Want Katy to call you? Reply KATY and we'll set it up."
        )

        sent_ok = False
        delivery_note = ""

        if delivery_method == "email":
            if not prospect_email:
                return {"result": "I can send this by email, but I still need the best email address."}
            from tools.gmail_tool import send_email
            res = send_email(
                to=prospect_email,
                subject="Your Requested Service Details",
                body=message,
                from_name="Katy Team",
            )
            sent_ok = bool(res.get("sent"))
            delivery_note = "email"
        else:
            if not prospect_phone:
                return {"result": "I can send this by text, but I still need the best mobile number."}
            from tools.sms_tool import send_sms
            res = send_sms(to_number=prospect_phone, body=message)
            sent_ok = bool(res.get("sent"))
            delivery_note = "sms"

        from memory.memory import get_prospects, update_prospect
        prospects = get_prospects()
        clean = prospect_phone.replace("+1", "").replace("-", "").replace(" ", "")
        match = next((p for p in prospects if clean and clean in str(p.get("phone", "")).replace("-", "").replace(" ", "")), None)
        if match:
            update_prospect(
                business_name=match["business_name"],
                location=match.get("location", ""),
                call_result_summary=f"Business details sent via {delivery_note}",
                notes=json.dumps({
                    "details_sent": details,
                    "delivery_method": delivery_note,
                    "business_name": business_name,
                }),
            )

        if sent_ok:
            log_event("vapi", "action", f"Business details sent via {delivery_note}: {business_name or prospect_phone}")
            return {"result": f"Done. I sent the requested details by {delivery_note}."}

        log_event("vapi", "thought", f"Business details delivery failed ({delivery_note}): {business_name or prospect_phone}")
        return {"result": "I prepared the details but delivery failed. I can retry now."}
    except Exception as e:
        log_event("vapi", "thought", f"send-business-details error: {e}")
        return {"result": "I hit a technical issue sending the details. Please try again in a moment."}


@app.post("/vapi/save-notes")
async def vapi_save_notes(body: dict):
    """Eric calls this at the end of every call to log structured outcome data."""
    try:
        params = body.get("message", {}).get("functionCall", {}).get("parameters", body)
        business_name = params.get("business_name", "")
        prospect_phone = params.get("prospect_phone", "")
        outcome = params.get("outcome", "")  # no_answer, busy, gatekeeper, qualified, not_interested, won, lost
        temperature = params.get("temperature", "warm")  # cold, cool, warm, hot
        notes = params.get("notes", "")
        objections = params.get("objections", "")
        requires_transfer = params.get("requires_transfer", False)
        opt_out = bool(params.get("opt_out", False))

        from memory.memory import get_prospects, update_prospect, get_availability
        prospects = get_prospects()
        clean = prospect_phone.replace("+1","").replace("-","").replace(" ","")
        match = next((p for p in prospects if clean in str(p.get("phone","")).replace("-","").replace(" ","")), None)

        # Determine next action based on outcome + availability
        katy_avail = get_availability()
        next_action = "do_not_call"  # default
        
        notes_blob = " ".join([str(notes), str(objections), str(outcome)]).lower()
        if any(token in notes_blob for token in ["opt out", "stop", "remove me", "do not call", "don't call", "dont call"]):
            opt_out = True

        if outcome == "qualified" and requires_transfer:
            if katy_avail.get("available_now"):
                next_action = "transfer_now"
            else:
                next_action = "schedule_callback"
        elif outcome in ("busy", "gatekeeper"):
            next_action = "schedule_callback"
        elif outcome == "not_interested":
            next_action = "do_not_call"
        elif outcome == "won":
            next_action = "close"
        elif outcome == "no_answer":
            next_action = "retry"

        if opt_out:
            outcome = "not_interested"
            next_action = "do_not_call"

        callback_due = params.get("callback_time", None)
        callback_reason = ""
        if next_action == "schedule_callback":
            if outcome == "busy":
                callback_reason = "busy"
            elif outcome == "gatekeeper":
                callback_reason = "decision_maker_unavailable"
            elif not katy_avail.get("available_now"):
                callback_reason = "katy_unavailable"

        if match:
            notes_text = json.dumps({
                "outcome": outcome,
                "temperature": temperature,
                "notes": notes,
                "objections": objections,
                "called_at": datetime.now(timezone.utc).isoformat(),
                "next_action": next_action,
            })
            update_prospect(
                business_name=match["business_name"],
                location=match.get("location",""),
                last_call_at=datetime.now(timezone.utc).isoformat(),
                last_call_outcome=outcome,
                call_result_summary=notes,
                call_temperature=temperature,
                objections=objections,
                next_action=next_action,
                callback_due_at=callback_due,
                callback_reason=callback_reason,
                callback_status="scheduled" if next_action == "schedule_callback" else "done",
                requires_human_transfer=1 if next_action == "transfer_now" else 0,
                transfer_status="ready" if next_action == "transfer_now" else "not_ready",
                call_attempts=int(match.get("call_attempts") or 0) + 1,
                pipeline_stage="do_not_call" if opt_out else outcome,
                opt_out_at=datetime.now(timezone.utc).isoformat() if opt_out else match.get("opt_out_at"),
                opt_out_reason="verbal_opt_out" if opt_out else match.get("opt_out_reason", ""),
                dnc_status="internal_opt_out" if opt_out else (match.get("dnc_status") or "clear"),
                dnc_checked_at=datetime.now(timezone.utc).isoformat(),
                dnc_source="vapi_eric" if opt_out else (match.get("dnc_source") or ""),
                notes=notes_text,
            )

            if opt_out:
                _record_dnc_entry(
                    prospect_phone,
                    match.get("business_name", business_name),
                    "verbal_opt_out",
                    source="vapi_eric",
                    notes=notes,
                )

        # Compute real buyer intent score from outcome + temperature
        _score_map = {
            ("won", "hot"): 10, ("won", "warm"): 10, ("won", "cold"): 9,
            ("qualified", "hot"): 9, ("qualified", "warm"): 7, ("qualified", "cool"): 6, ("qualified", "cold"): 5,
            ("busy", "hot"): 6, ("busy", "warm"): 5, ("busy", "cool"): 4, ("busy", "cold"): 3,
            ("gatekeeper", "warm"): 4, ("gatekeeper", "cold"): 3,
            ("no_answer", "warm"): 3, ("no_answer", "cold"): 2,
            ("not_interested", "cold"): 1, ("lost", "cold"): 1,
        }
        _temp_fallback = {"hot": 8, "warm": 5, "cool": 3, "cold": 2}
        buyer_intent_score = _score_map.get(
            (outcome, temperature),
            _temp_fallback.get(str(temperature).lower(), 3)
        )

        if match:
            from memory.memory import update_prospect as _up
            _up(business_name=match["business_name"], location=match.get("location", ""), buyer_intent_score=buyer_intent_score)

        # Push updated prospect back to Google Sheet
        from tools.sheets_tool import push_prospect_sync
        _sheet_prospect = {
            "business_name": business_name,
            "phone": prospect_phone,
            "buyer_intent_score": buyer_intent_score,
            "call_temperature": temperature,
            "last_call_outcome": outcome,
            "call_result_summary": notes,
            "objections": objections,
            "next_action": next_action,
            "last_call_at": datetime.now(timezone.utc).isoformat(),
        }
        if match:
            _sheet_prospect.update({k: match.get(k, "") for k in ["location", "niche", "priority", "website"]})
        try:
            push_prospect_sync(_sheet_prospect)
        except Exception:
            pass

        action_emoji = {"transfer_now": "🤝", "schedule_callback": "📅", "do_not_call": "🛑", "retry": "🔄", "close": "✅"}.get(next_action, "—")
        log_event("vapi", "action", f"Call saved: {business_name} — {outcome} ({temperature}) score={buyer_intent_score} — {action_emoji} Next: {next_action}")
        log_compliance_event("call_outcomes", "saved", {
            "business_name": business_name,
            "prospect_phone": _normalize_phone(prospect_phone),
            "outcome": outcome,
            "next_action": next_action,
            "opt_out": opt_out,
        })
        return {"result": f"Notes saved. Next action: {next_action}"}
    except Exception as e:
        return {"result": f"Notes saved. ({e})"}


@app.post("/vapi/send-payment-link")
async def vapi_send_payment_link(body: dict):
    """Eric calls this when a prospect is ready to pay and chooses SMS or email delivery."""
    try:
        params = body.get("message", {}).get("functionCall", {}).get("parameters", body)
        business_name = params.get("business_name", "")
        prospect_phone = params.get("prospect_phone", "")
        prospect_email = params.get("prospect_email", "")
        contact_name = params.get("contact_name", "")
        delivery_method = str(params.get("delivery_method", "sms")).strip().lower()
        amount = float(params.get("amount", 1000))

        from tools.stripe_tool import create_payment_link
        from tools.gmail_tool import send_email
        from tools.sms_tool import send_sms

        link = create_payment_link(
            amount_dollars=amount,
            description=f"AI Sales Agent Setup Deposit - {business_name or 'New Client'}",
            customer_email=prospect_email or None,
            metadata={
                "business_name": business_name,
                "prospect_phone": prospect_phone,
                "delivery_method": delivery_method,
                "contact_name": contact_name,
                "source": "vapi_eric",
            },
        )

        payment_url = link.get("url")
        if not payment_url:
            err = link.get("error", "Could not create payment link")
            log_event("vapi", "thought", f"Payment link failed: {err}")
            return {"result": f"I could not generate the payment link right now. Please try again shortly. ({err})"}

        message = (
            f"Hi{(' ' + contact_name) if contact_name else ''}, here is your secure payment link for the 50% setup deposit "
            f"(${amount:,.0f}) to start your AI sales agent build: {payment_url}"
        )

        sent_ok = False
        delivery_note = ""

        if delivery_method == "email":
            if not prospect_email:
                return {"result": "I can send it by email, but I still need the best email address."}
            email_res = send_email(
                to=prospect_email,
                subject="Your AI Sales Agent Setup Deposit Link",
                body=message,
                from_name="Katy Team",
            )
            sent_ok = bool(email_res.get("sent"))
            delivery_note = "email"
        else:
            if not prospect_phone:
                return {"result": "I can send it by SMS, but I still need the best mobile number."}
            sms_res = send_sms(to_number=prospect_phone, body=message)
            sent_ok = bool(sms_res.get("sent"))
            delivery_note = "sms"

        from memory.memory import get_prospects, update_prospect
        prospects = get_prospects()
        clean = prospect_phone.replace("+1", "").replace("-", "").replace(" ", "")
        match = next((p for p in prospects if clean and clean in str(p.get("phone", "")).replace("-", "").replace(" ", "")), None)
        if match:
            update_prospect(
                business_name=match["business_name"],
                location=match.get("location", ""),
                stripe_deposit_link=payment_url,
                deposit_amount=amount,
                next_action="await_deposit",
                call_result_summary=f"Payment link sent via {delivery_note}",
                notes=json.dumps({
                    "payment_link": payment_url,
                    "delivery_method": delivery_note,
                    "prospect_email": prospect_email,
                    "prospect_phone": prospect_phone,
                    "business_name": business_name,
                    "amount": amount,
                }),
            )

        if sent_ok:
            log_event("vapi", "action", f"Payment link sent via {delivery_note}: {business_name or prospect_phone}")
            return {"result": f"Done. I just sent the secure payment link by {delivery_note}."}

        log_event("vapi", "thought", f"Payment link created but delivery failed ({delivery_note}): {business_name or prospect_phone}")
        return {"result": "I generated the payment link but delivery failed. I can retry now if you want."}
    except Exception as e:
        log_event("vapi", "thought", f"send-payment-link error: {e}")
        return {"result": "I hit a technical issue sending the payment link. Please try again in a moment."}


@app.post("/vapi/send-sms")
async def vapi_send_sms(body: dict):
    """Eric calls this to send an SMS directly to the prospect for quick updates or follow-ups."""
    try:
        params = body.get("message", {}).get("functionCall", {}).get("parameters", body)
        to_number = params.get("to_number", "")
        sms_body = params.get("body", "")
        contact_name = params.get("contact_name", "")

        if not to_number:
            return {"result": "I need a phone number to send the text."}

        if not sms_body:
            return {"result": "I need the message text to send."}

        from tools.sms_tool import send_sms
        res = send_sms(to_number=to_number, body=sms_body)

        if res.get("sent"):
            log_event("vapi", "action", f"SMS sent to {to_number}: {contact_name or 'prospect'}")
            return {
                "result": f"SMS delivered to {to_number}.",
                "sent": True,
                "phone": to_number,
            }
        else:
            error_msg = res.get("error", "Unknown error")
            log_event("vapi", "thought", f"SMS delivery failed: {error_msg}")
            return {
                "result": f"SMS failed to send: {error_msg}. Want me to retry?",
                "sent": False,
                "error": error_msg,
            }

    except Exception as e:
        log_event("vapi", "thought", f"send-sms error: {e}")
        return {"result": f"I hit a technical issue sending the SMS. Error: {str(e)}"}


@app.post("/vapi/send-email")
async def vapi_send_email(body: dict):
    """Eric calls this to send an email directly to the prospect for detailed information or formal communication."""
    try:
        params = body.get("message", {}).get("functionCall", {}).get("parameters", body)
        to = params.get("to", "")
        subject = params.get("subject", "")
        email_body = params.get("body", "")
        contact_name = params.get("contact_name", "")

        if not to:
            return {"result": "I need an email address to send the message."}

        if not subject:
            return {"result": "I need a subject line for the email."}

        if not email_body:
            return {"result": "I need the message body for the email."}

        from tools.gmail_tool import send_email
        res = send_email(
            to=to,
            subject=subject,
            body=email_body,
            from_name="Katy Team",
            reply_to=os.getenv("GMAIL_ADDRESS", ""),
        )

        if res.get("sent"):
            log_event("vapi", "action", f"Email sent to {to}: Subject '{subject}'")
            return {
                "result": f"Email sent to {to}.",
                "sent": True,
                "email": to,
                "subject": subject,
            }
        else:
            error_msg = res.get("error", "Unknown error")
            log_event("vapi", "thought", f"Email delivery failed: {error_msg}")
            return {
                "result": f"Email failed to send: {error_msg}. Want me to retry?",
                "sent": False,
                "error": error_msg,
            }

    except Exception as e:
        log_event("vapi", "thought", f"send-email error: {e}")
        return {"result": f"I hit a technical issue sending the email. Error: {str(e)}"}


@app.get("/vapi/active")
async def vapi_active_calls():
    """Get currently active VAPI calls with their listen URLs."""
    import httpx
    key = os.getenv("VAPI_API_KEY","")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Fetch most recent calls and filter for in-progress
            r = await client.get("https://api.vapi.ai/call?limit=20",
                headers={"Authorization": f"Bearer {key}"})
            calls = r.json()
            if isinstance(calls, list):
                active = [c for c in calls if c.get("status") in ("in-progress", "ringing", "queued")]
                return {"calls": [{"id": c.get("id"), "status": c.get("status"),
                    "business": c.get("customer",{}).get("name","Unknown"),
                    "phone": c.get("customer",{}).get("number",""),
                    "listen_url": c.get("monitor",{}).get("listenUrl",""),
                    "started_at": c.get("startedAt","")} for c in active]}
            return {"calls": [], "raw": calls}
    except Exception as e:
        return {"calls": [], "error": str(e)}


@app.get("/vapi/calls")
async def get_call_log():
    """Get all prospects with call history."""
    from memory.memory import get_prospects
    prospects = get_prospects()
    called = [p for p in prospects if p.get("call_outcome") or p.get("last_called") or p.get("callback_time")]
    return {"calls": called, "total": len(called)}


@app.post("/vapi/webhook")
async def vapi_webhook(body: dict):
    """
    General VAPI webhook — handles call events (started, ended, transferred).
    """
    event_type = body.get("message", {}).get("type", "")
    call_id = body.get("message", {}).get("call", {}).get("id", "")

    if event_type == "end-of-call-report":
        msg = body.get("message", {})
        summary = msg.get("summary", "")
        ended_reason = msg.get("endedReason", "")
        transcript = msg.get("transcript", "")
        recording_url = msg.get("recordingUrl", "")
        structured = msg.get("analysis", {}).get("structuredData", {})
        customer = msg.get("call", {}).get("customer", {})
        prospect_phone = customer.get("number", "").replace("+1","")
        business_name = msg.get("call", {}).get("metadata", {}).get("business_name", "")

        # Save to prospect record
        if business_name or prospect_phone:
            from memory.memory import get_prospects, update_prospect
            prospects = get_prospects()
            clean = prospect_phone.replace("-","").replace(" ","")
            match = next((p for p in prospects if clean in str(p.get("phone","")).replace("-","").replace(" ","")), None)
            if match:
                call_notes = json.dumps({
                    "summary": summary,
                    "outcome": structured.get("outcome", ""),
                    "temperature": structured.get("temperature", ""),
                    "callback_time": structured.get("callback_time", ""),
                    "objections": structured.get("objections", []),
                    "key_quote": structured.get("key_quote", ""),
                    "recording_url": recording_url,
                    "called_at": datetime.now(timezone.utc).isoformat(),
                })
                update_prospect(
                    business_name=match["business_name"],
                    location=match.get("location",""),
                    pipeline_stage=structured.get("outcome", ended_reason),
                    notes=call_notes,
                )

        log_event("vapi", "action",
            f"Call ended — {business_name} — {ended_reason} — {structured.get('temperature','?')} — {summary[:120]}")

    elif event_type == "transfer":
        log_event("vapi", "action", f"Call transferred to Katy ✅")

    return {"received": True}


@app.post("/vapi/setup")
async def vapi_setup(body: dict):
    """
    One-time setup — creates the VAPI assistant and saves the ID to .env
    Body: { "katy_phone": "3043989553", "webhook_url": "https://your-ngrok-url.ngrok.io" }
    """
    from tools.vapi_tool import create_assistant, list_phone_numbers
    katy_phone = body.get("katy_phone", "3043989553")
    webhook_url = body.get("webhook_url", "http://localhost:8000")

    # Update webhook URL in tool
    import tools.vapi_tool as vt
    for key in vt.PITCH_SCRIPTS:
        pass  # webhook is set via env var

    phone_numbers = await list_phone_numbers()
    phone_number_id = ""
    if isinstance(phone_numbers, list) and len(phone_numbers) > 0:
        phone_number_id = phone_numbers[0].get("id", "")

    assistant = await create_assistant(phone_number_id, katy_phone, webhook_url=webhook_url)
    assistant_id = assistant.get("id", "")

    log_event("vapi", "action", f"Assistant created: {assistant_id}")
    return {
        "assistant_id": assistant_id,
        "phone_number_id": phone_number_id,
        "next_step": f"Add to .env: VAPI_ASSISTANT_ID={assistant_id} and VAPI_PHONE_NUMBER_ID={phone_number_id}"
    }


@app.post("/sms/inbound")
async def sms_inbound(request: Request):
    """
    Twilio posts here when someone texts your Twilio number.
    Handles: opt-outs, replies from prospects, and notifies Katy via Telegram.
    Twilio sends form-encoded data, not JSON.
    """
    from urllib.parse import unquote_plus

    body_bytes = await request.body()
    raw = body_bytes.decode("utf-8", errors="ignore")

    # Parse form-encoded Twilio payload
    params = {}
    for pair in raw.split("&"):
        if "=" in pair:
            k, _, v = pair.partition("=")
            params[unquote_plus(k)] = unquote_plus(v)

    from_number = params.get("From", "")
    to_number   = params.get("To", "")
    message_body = params.get("Body", "").strip()

    log_event("sms", "action", f"Inbound SMS from {from_number}: {message_body[:120]}")

    # ── Opt-out handling (legally required) ──────────────────────────────────
    opt_out_keywords = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit"}
    opt_in_keywords  = {"start", "unstop", "yes"}
    msg_lower = message_body.lower().strip()

    if msg_lower in opt_out_keywords:
        from memory.memory import get_prospects, update_prospect
        prospects = get_prospects()
        match = next((p for p in prospects if _phones_match(p.get("phone", ""), from_number)), None)
        if match:
            update_prospect(
                business_name=match["business_name"],
                location=match.get("location", ""),
                pipeline_stage="opted_out",
                next_action="do_not_contact",
            )
            log_event("sms", "action", f"Opt-out recorded for {from_number} ({match['business_name']})")

        # Twilio expects TwiML response — empty response confirms opt-out silently
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml",
        )

    # ── Look up who this is ───────────────────────────────────────────────────
    from memory.memory import get_prospects
    prospects = get_prospects()
    match = next((p for p in prospects if _phones_match(p.get("phone", ""), from_number)), None)
    biz_name    = match["business_name"] if match else "Unknown"
    biz_city    = match.get("location", "") if match else ""
    temperature = match.get("call_temperature", "") if match else ""

    # ── Notify Katy via Telegram ──────────────────────────────────────────────
    try:
        from scheduler import send_telegram
        temp_tag = f" [{temperature.upper()}]" if temperature else ""
        tg_msg = (
            f"📱 <b>SMS Reply{temp_tag}</b>\n"
            f"From: {from_number}\n"
            f"Business: {biz_name}" + (f" — {biz_city}" if biz_city else "") + "\n"
            f"\n<i>{message_body}</i>"
        )
        await send_telegram(tg_msg)
    except Exception as e:
        log_event("sms", "warn", f"Telegram notify failed: {e}")

    # ── Save reply to prospect record ─────────────────────────────────────────
    if match:
        from memory.memory import update_prospect
        existing_notes = match.get("call_result_summary", "") or ""
        appended = f"{existing_notes}\n[SMS reply] {message_body}".strip()
        update_prospect(
            business_name=match["business_name"],
            location=match.get("location", ""),
            call_result_summary=appended[:1000],
            pipeline_stage="replied_sms",
        )

    # ── Auto-draft a reply via sales agent (background, non-blocking) ─────────
    async def _draft_sms_reply():
        try:
            context_summary = (
                f"Prospect: {biz_name}" + (f" in {biz_city}" if biz_city else "") +
                (f" | Temperature: {temperature}" if temperature else "") +
                f"\nTheir SMS: {message_body}"
            )
            if match:
                notes = match.get("call_result_summary", "") or ""
                if notes:
                    context_summary += f"\nConversation history: {notes[:400]}"

            draft = await task_handler.run_agent(
                "sales",
                f"A prospect just replied to our SMS outreach. Draft a natural, concise reply "
                f"(max 160 chars for SMS, or a short paragraph for follow-up). "
                f"Move them forward — toward a call, demo, or close. "
                f"Sound like a real human, not a script.\n\n{context_summary}"
            )
            request_approval(
                agent="sales",
                action="send_sms_reply",
                details={
                    "to": from_number,
                    "business": biz_name,
                    "their_message": message_body,
                    "draft_reply": draft,
                }
            )
            try:
                from scheduler import send_telegram
                tg = (
                    f"✏️ <b>SMS Draft Ready</b> — {biz_name}\n"
                    f"Their message: <i>{message_body[:120]}</i>\n\n"
                    f"<b>Suggested reply:</b>\n{draft[:300]}\n\n"
                    f"Reply YES in /approvals to send."
                )
                await send_telegram(tg)
            except Exception:
                pass
        except Exception as e:
            log_event("sms", "warn", f"Auto-draft failed: {e}")

    asyncio.create_task(_draft_sms_reply())

    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """
    Stripe posts here when a payment is completed.
    When a client pays the 50% deposit, Katy gets notified immediately via Telegram + SMS.
    Set this URL in Stripe Dashboard → Developers → Webhooks.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    try:
        import stripe as _stripe
        _stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

        if webhook_secret:
            event = _stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        else:
            import json
            event = json.loads(payload)

        if event.get("type") in ("payment_intent.succeeded", "checkout.session.completed", "payment_link.completed"):
            data = event.get("data", {}).get("object", {})
            amount = data.get("amount_received") or data.get("amount_total") or 0
            amount_dollars = amount / 100
            customer_email = (
                data.get("customer_email")
                or data.get("receipt_email")
                or (data.get("customer_details") or {}).get("email")
                or "unknown"
            )
            meta = data.get("metadata") or {}
            business_name = meta.get("business_name") or customer_email
            contact_name = meta.get("contact_name") or ""

            msg = (
                f"💰 DEPOSIT RECEIVED — ${amount_dollars:,.2f}\n"
                f"Client: {business_name}"
                + (f" ({contact_name})" if contact_name else "")
                + f"\nEmail: {customer_email}\n"
                f"Begin building within 24 hours."
            )

            log_event("stripe", "action", msg)

            # Notify via Telegram
            katy_id = os.getenv("KATY_TELEGRAM_ID", "")
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            if katy_id and bot_token:
                try:
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            f"https://api.telegram.org/bot{bot_token}/sendMessage",
                            json={"chat_id": katy_id, "text": msg},
                            timeout=10,
                        )
                except Exception:
                    pass

            # Notify via SMS
            katy_phone = os.getenv("KATY_PHONE", "")
            if katy_phone:
                try:
                    from tools.sms_tool import send_sms
                    send_sms(to_number=katy_phone, body=msg[:160])
                except Exception:
                    pass

            # Update prospect in Google Sheet
            try:
                from tools.sheets_tool import push_prospect_sync
                push_prospect_sync({
                    "business_name": business_name,
                    "phone": meta.get("prospect_phone", ""),
                    "last_call_outcome": "won",
                    "call_temperature": "hot",
                    "buyer_intent_score": 10,
                    "next_action": "build",
                    "call_result_summary": f"Deposit paid ${amount_dollars:,.2f}",
                })
            except Exception:
                pass

        return {"received": True}

    except Exception as e:
        log_event("stripe", "warn", f"Webhook error: {e}")
        return {"received": False, "error": str(e)}


@app.post("/gmail/poll-replies")
async def gmail_poll_replies(since_hours: int = 48):
    """
    Check Gmail inbox for unread replies from prospects.
    For each reply, drafts a response via the sales agent and queues for Katy's approval.
    Trigger manually or via a cron.
    """
    from tools.gmail_tool import check_replies
    from memory.memory import get_prospects

    replies = check_replies(since_hours=since_hours)
    errors  = [r for r in replies if "error" in r]
    if errors:
        return {"checked": False, "error": errors[0]["error"]}

    real_replies = [r for r in replies if "error" not in r]
    if not real_replies:
        return {"checked": True, "new_replies": 0}

    prospects = get_prospects()
    processed = []

    for reply in real_replies:
        from_email = reply.get("from_email", "")
        from_name  = reply.get("from_name", "")
        body       = reply.get("body", "")
        subject    = reply.get("subject", "")

        # Try to match to a known prospect by email
        match = next(
            (p for p in prospects if from_email.lower() in (p.get("email", "") or "").lower()),
            None
        )
        biz_name = match["business_name"] if match else (from_name or from_email)

        log_event("gmail", "action", f"Reply from {from_email} ({biz_name}): {body[:80]}")

        # Draft reply via sales agent
        context = (
            f"Prospect: {biz_name}\n"
            f"Their email subject: {subject}\n"
            f"Their message:\n{body[:1000]}"
        )
        if match:
            notes = match.get("call_result_summary", "") or ""
            if notes:
                context += f"\n\nConversation history: {notes[:300]}"

        try:
            draft = await task_handler.run_agent(
                "sales",
                f"A prospect just replied to our email outreach. Write a concise, human reply "
                f"that moves them forward — toward a call, demo, or close. "
                f"Match their tone. No fluff.\n\n{context}"
            )

            request_approval(
                agent="sales",
                action="send_email_reply",
                details={
                    "to": from_email,
                    "business": biz_name,
                    "their_subject": subject,
                    "their_message": body[:400],
                    "draft_reply": draft,
                }
            )

            # Notify Katy via Telegram
            try:
                from scheduler import send_telegram
                tg = (
                    f"📧 <b>Email Reply — {biz_name}</b>\n"
                    f"From: {from_email}\n"
                    f"Subject: {subject}\n"
                    f"<i>{body[:150]}</i>\n\n"
                    f"<b>Draft reply:</b>\n{draft[:300]}\n\n"
                    f"Approve in /approvals to send."
                )
                await send_telegram(tg)
            except Exception:
                pass

            processed.append({"from": from_email, "business": biz_name, "drafted": True})

            # Save reply to prospect record
            if match:
                from memory.memory import update_prospect
                existing = match.get("call_result_summary", "") or ""
                updated  = f"{existing}\n[Email reply] {body[:300]}".strip()
                update_prospect(
                    business_name=match["business_name"],
                    location=match.get("location", ""),
                    call_result_summary=updated[:1000],
                    pipeline_stage="replied_email",
                )

        except Exception as e:
            processed.append({"from": from_email, "business": biz_name, "drafted": False, "error": str(e)})

    return {"checked": True, "new_replies": len(real_replies), "processed": processed}


@app.post("/browser/login/{platform}")
async def browser_login(platform: str):
    """
    Opens a visible browser window so Katy can log into LinkedIn, Facebook, or Instagram.
    Saves the session — agents will use it for outreach.
    Supported platforms: linkedin, facebook, instagram
    """
    from tools.browser import browser_tool
    if not browser_tool.browser:
        started = await browser_tool.start()
        if not started:
            return {"ok": False, "error": "Playwright not available"}

    result = await browser_tool.login_flow(platform)
    return {"ok": True, "message": result}


@app.post("/browser/send-dm")
async def browser_send_dm(request: Request):
    """
    Send a direct message as Katy via LinkedIn, Facebook, or Instagram.
    Body: {platform, target, message}
      - linkedin:  target = profile URL
      - facebook:  target = page/profile URL
      - instagram: target = @username (no @)
    Requires the session for that platform to be saved first via /browser/login/{platform}.
    """
    data = await request.json()
    platform = (data.get("platform") or "").lower().strip()
    target   = (data.get("target") or "").strip()
    message  = (data.get("message") or "").strip()

    if not platform or not target or not message:
        return {"sent": False, "error": "platform, target, and message are required"}

    from tools.browser import browser_tool
    if not browser_tool.browser:
        await browser_tool.start()

    if platform == "linkedin":
        result = await browser_tool.linkedin_send_dm(target, message)
    elif platform == "facebook":
        result = await browser_tool.facebook_send_message(target, message)
    elif platform == "instagram":
        result = await browser_tool.instagram_send_dm(target, message)
    else:
        return {"sent": False, "error": f"Unknown platform: {platform}. Use linkedin, facebook, or instagram."}

    log_event("outreach", "action", f"DM via {platform} to {target}: sent={result.get('sent')}")
    return result


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
