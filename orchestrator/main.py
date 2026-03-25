from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import uvicorn, json, os, asyncio
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

from agents.coordinator import CoordinatorAgent
from agents.research import ResearchAgent
from agents.small_biz_expert import SmallBizExpertAgent
from agents.sales import SalesAgent, SalesOpsAgent
from agents.outreach import OutreachAgent
from agents.engineer import EngineerAgent
from agents.gbp_scout import GBPScoutAgent
from agents.gbp_researcher import GBPResearcherAgent
from agents.gbp_sales import GBPSalesAgent
from agents.team_leader import TeamLeaderAgent
from agents.job_seeker import JobSeekerAgent
from agents.scout import ScoutAgent
from agents.networking import NetworkingAgent
from agents.coach import CoachAgent
from agents.interview_coach import InterviewCoachAgent
from agents.lead_gen import LeadGenAgent
from agents.marketing import MarketingAgent
from agents.biz_dev import BizDevAgent
from agents.automations import AutomationsAgent
from agents.solutions_architect import SolutionsArchitectAgent
from agents.resume_builder import ResumeBuilderAgent
from agents.research_assistant import ResearchAssistantAgent
from scheduler import scheduler
from memory.memory import init_db, get_memory_summary
from task_handler import TaskHandler
from constants import ALLOWED_TARGET_NICHES, DEFAULT_TARGET_NICHE, MAX_PROSPECT_SCORE

MEMORY_PATH = Path("/app/memory/katy_brief.md")
KATY_BRIEF = MEMORY_PATH.read_text() if MEMORY_PATH.exists() else ""
LOG_DIR = Path("/app/logs")
LOG_DIR.mkdir(exist_ok=True)

event_stream = []
approval_queue = []
scheduled_events = []
scheduled_events_lock = asyncio.Lock()
scheduled_events_runner = None

# Full agent roster — GBP sales crew + general-purpose agents
AGENT_MAP = {
    # ── GBP sales pipeline ───────────────────────────────
    "coordinator":          lambda b,l,a: CoordinatorAgent(b,l,a),
    "gbp_scout":            lambda b,l,a: GBPScoutAgent(b,l,a),
    "gbp_researcher":       lambda b,l,a: GBPResearcherAgent(b,l,a),
    "gbp_sales":            lambda b,l,a: GBPSalesAgent(b,l,a),
    "outreach":             lambda b,l,a: OutreachAgent(b,l,a),
    "sales":                lambda b,l,a: SalesAgent(b,l,a),
    "sales_ops":            lambda b,l,a: SalesOpsAgent(b,l,a),
    # ── General-purpose agents ───────────────────────────
    "small_biz_expert":     lambda b,l,a: SmallBizExpertAgent(b,l,a),
    "research":             lambda b,l,a: ResearchAgent(b,l,a),
    "research_assistant":   lambda b,l,a: ResearchAssistantAgent(b,l,a),
    "engineer":             lambda b,l,a: EngineerAgent(b,l,a),
    "team_leader":          lambda b,l,a: TeamLeaderAgent(b,l,a),
    "job_seeker":           lambda b,l,a: JobSeekerAgent(b,l,a),
    "scout":                lambda b,l,a: ScoutAgent(b,l,a),
    "networking":           lambda b,l,a: NetworkingAgent(b,l,a),
    "coach":                lambda b,l,a: CoachAgent(b,l,a),
    "interview_coach":      lambda b,l,a: InterviewCoachAgent(b,l,a),
    "lead_gen":             lambda b,l,a: LeadGenAgent(b,l,a),
    "marketing":            lambda b,l,a: MarketingAgent(b,l,a),
    "biz_dev":              lambda b,l,a: BizDevAgent(b,l,a),
    "automations":          lambda b,l,a: AutomationsAgent(b,l,a),
    "solutions_architect":  lambda b,l,a: SolutionsArchitectAgent(b,l,a),
    "resume_builder":       lambda b,l,a: ResumeBuilderAgent(b,l,a),
}

def log_event(agent: str, event_type: str, content: str):
    event = {"id": len(event_stream)+1, "timestamp": datetime.now().isoformat(),
             "agent": agent, "type": event_type, "content": content}
    event_stream.append(event)
    with open(LOG_DIR / "events.jsonl", "a") as f:
        f.write(json.dumps(event) + "\n")
    return event

def request_approval(agent: str, action: str, details: dict):
    item = {"id": len(approval_queue)+1, "timestamp": datetime.now().isoformat(),
            "agent": agent, "action": action, "details": details, "status": "pending"}
    approval_queue.append(item)
    log_event(agent, "approval_needed", f"{action}: {json.dumps(details)}")
    return item


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

@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduled_events_runner
    init_db()
    _load_scheduled_events()
    scheduled_events_runner = asyncio.create_task(_scheduled_events_loop())
    log_event("system", "thought", f"Agent team starting up — {len(AGENT_MAP)} agents loading...")
    log_event("system", "thought", f"Katy's brief loaded ({len(KATY_BRIEF)} chars)")
    # DISABLED: Auto scheduler — only manual API calls trigger now
    # asyncio.create_task(scheduler.start())
    log_event("system", "thought", "⚙️ Manual-only mode: waiting for your API requests")
    yield
    if scheduled_events_runner:
        scheduled_events_runner.cancel()
    scheduler.stop()

app = FastAPI(title="Katy Agent Team", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/dashboard")
def dashboard():
    # Try container path first, then local dev path
    for candidate in [
        Path("/app/dashboard/index.html"),
        Path(__file__).parent.parent / "dashboard.html",
        Path("dashboard.html"),
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
        return {"result": result}
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
    session_dir = Path("/app/sessions")
    return {"linkedin": (session_dir/"linkedin_session.json").exists(),
            "facebook": (session_dir/"facebook_session.json").exists()}

@app.post("/gbp-pipeline")
async def gbp_pipeline(body: dict):
    """
    Full GBP sales pipeline: Scout → Research → Outreach draft → Await approval.
    body: {"niche": "plumbers", "location": "Austin TX", "limit": 15}
    """
    niche = body.get("niche", DEFAULT_TARGET_NICHE)
    if not _is_allowed_niche(niche):
        original_niche = niche
        niche = DEFAULT_TARGET_NICHE
        log_event("task_handler", "action", f"Blocked niche '{original_niche}' — using {DEFAULT_TARGET_NICHE}")
    location = body.get("location", "United States")
    limit = body.get("limit", 15)

    task = f"Find {niche} in {location} with missing or incomplete Google Business Profiles. Scan up to {limit} businesses."
    log_event("task_handler", "action", f"GBP pipeline: {niche} in {location}")

    handler = make_task_handler()

    scout_result = await handler.run_agent("gbp_scout", task)
    results = {"gbp_scout": scout_result}

    scout_text = str(scout_result or "")
    if "GBP SCOUT FAILED" in scout_text:
        return {
            "results": results,
            "niche": niche,
            "location": location,
            "pipeline_status": "halted_at_scout",
        }

    chained_context = f"Original task: {task}\n\n[gbp_scout findings]\n{scout_result}"
    researcher_result = await handler.run_agent("gbp_researcher", chained_context)
    results["gbp_researcher"] = researcher_result

    researcher_text = str(researcher_result or "")
    if "GBP RESEARCHER SKIPPED" in researcher_text:
        return {
            "results": results,
            "niche": niche,
            "location": location,
            "pipeline_status": "halted_at_research",
        }

    outreach_context = (
        f"Original task: {task}\n\n"
        f"[gbp_scout findings]\n{scout_result}\n\n"
        f"[gbp_researcher findings]\n{researcher_result}"
    )
    results["outreach"] = await handler.run_agent("outreach", outreach_context)

    return {
        "results": results,
        "niche": niche,
        "location": location,
        "pipeline_status": "completed",
    }


@app.post("/gbp-propose")
async def gbp_propose(body: dict):
    """
    Generate and queue proposals for researched prospects.
    Requires Katy's approval before sending.
    """
    task = body.get("task", "Generate proposals for all researched GBP prospects")
    log_event("gbp_sales", "action", "Generating proposals")
    handler = make_task_handler()
    results = await handler.dispatch(["gbp_sales"], task)
    return {"results": results}


@app.post("/gbp-send-approved")
async def gbp_send_approved(body: dict):
    """
    After Katy approves an outreach draft, actually send it.
    body: {"prospect_name": "...", "location": "...", "email": "...", "subject": "...", "body": "..."}
    """
    prospect_name = body.get("prospect_name", "")
    location = body.get("location", "")
    email = body.get("email", "")
    subject = body.get("subject", "Quick question about your Google listing")
    message_body = body.get("body", "")

    log_event("outreach", "action", f"Sending approved email to {prospect_name}")
    outreach = OutreachAgent(KATY_BRIEF, log_event, request_approval)
    result = await outreach.send_approved_outreach(prospect_name, location, email, subject, message_body)
    return result


@app.get("/prospects")
def get_prospects_list(stage: str = None, priority: str = None):
    from memory.memory import get_prospects
    return get_prospects(stage=stage, priority=priority)

@app.patch("/prospects/{prospect_id}")
def patch_prospect(prospect_id: int, body: dict):
    """Update any fields on a prospect by ID."""
    from memory.memory import get_db
    allowed = {"owner_name","phone","email","website","priority","pipeline_stage",
               "research_notes","notes","niche","outreach_draft"}
    updates = {k:v for k,v in body.items() if k in allowed and v is not None}
    if not updates:
        return {"updated": False, "reason": "no valid fields"}
    conn = get_db()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    set_clause += ", updated_at=datetime('now')"
    conn.execute(f"UPDATE prospects SET {set_clause} WHERE id=?",
                 list(updates.values()) + [prospect_id])
    conn.commit()
    conn.close()
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

    # Auto-fill from prospect database if phone matches
    prospect_phone = body.get("prospect_phone", "")
    all_prospects = get_prospects(limit=500)
    prospect_data = _find_matching_prospect(prospect_phone, all_prospects)
    call_spec = _build_vapi_call_spec(body, prospect_data)

    result = await make_call(**call_spec)
    business_name = call_spec.get("business_name") or body.get("business_name") or "unknown prospect"
    log_event("vapi", "action", f"Call triggered to {business_name} — {result.get('id', 'error')}")
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
    log_event("vapi", "warn", f"get-prospect: no DB match for phone {phone!r} — returning safe fallback")
    return {"result": json.dumps({"owner_name": "business owner", "business_name": "", "prospect_not_found": True})}


@app.post("/vapi/schedule-callback")
async def vapi_schedule_callback(body: dict):
    """Eric calls this when a prospect asks for a callback."""
    try:
        params = body.get("message", {}).get("functionCall", {}).get("parameters", body)
        callback_time = params.get("callback_time", "")
        prospect_phone = params.get("prospect_phone", "")
        business_name = params.get("business_name", "")
        reason = params.get("reason", "")

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
                notes=notes_text,
            )

        log_event("vapi", "action", f"Callback scheduled: {business_name} — {callback_time}")
        return {"result": f"Callback scheduled for {callback_time}. I'll make sure Katy follows up then."}
    except Exception as e:
        return {"result": f"Callback noted. ({e})"}


@app.post("/vapi/save-notes")
async def vapi_save_notes(body: dict):
    """Eric calls this at the end of every call to log what happened."""
    try:
        params = body.get("message", {}).get("functionCall", {}).get("parameters", body)
        business_name = params.get("business_name", "")
        prospect_phone = params.get("prospect_phone", "")
        outcome = params.get("outcome", "")
        temperature = params.get("temperature", "")
        notes = params.get("notes", "")
        objections = params.get("objections", "")

        from memory.memory import get_prospects, update_prospect
        prospects = get_prospects()
        clean = prospect_phone.replace("+1","").replace("-","").replace(" ","")
        match = next((p for p in prospects if clean in str(p.get("phone","")).replace("-","").replace(" ","")), None)

        if match:
            notes_text = json.dumps({
                "outcome": outcome,
                "temperature": temperature,
                "notes": notes,
                "objections": objections,
                "called_at": datetime.now(timezone.utc).isoformat(),
            })
            update_prospect(
                business_name=match["business_name"],
                location=match.get("location",""),
                pipeline_stage=outcome,
                notes=notes_text,
            )

        log_event("vapi", "action", f"Call notes saved: {business_name} — {outcome} ({temperature}) — {notes[:80]}")
        return {"result": "Notes saved successfully."}
    except Exception as e:
        return {"result": f"Notes saved. ({e})"}


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


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)