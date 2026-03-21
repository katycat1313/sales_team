from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import uvicorn, json, os, asyncio
from datetime import datetime
from pathlib import Path

from agents.coordinator import CoordinatorAgent
from agents.research import ResearchAgent
from agents.small_biz_expert import SmallBizExpertAgent
from agents.sales import SalesAgent, SalesOpsAgent
from agents.outreach import OutreachAgent
from agents.engineer import EngineerAgent
from agents.gbp_scout import GBPScoutAgent
from agents.gbp_researcher import GBPResearcherAgent
from agents.gbp_sales import GBPSalesAgent
from scheduler import scheduler
from memory.memory import init_db, get_memory_summary
from task_handler import TaskHandler

MEMORY_PATH = Path("/app/memory/katy_brief.md")
KATY_BRIEF = MEMORY_PATH.read_text() if MEMORY_PATH.exists() else ""
LOG_DIR = Path("/app/logs")
LOG_DIR.mkdir(exist_ok=True)

event_stream = []
approval_queue = []

# Elite GBP sales crew — 9 agents, one mission: close clients
AGENT_MAP = {
    "coordinator":     lambda b,l,a: CoordinatorAgent(b,l,a),
    "gbp_scout":       lambda b,l,a: GBPScoutAgent(b,l,a),
    "gbp_researcher":  lambda b,l,a: GBPResearcherAgent(b,l,a),
    "gbp_sales":       lambda b,l,a: GBPSalesAgent(b,l,a),
    "outreach":        lambda b,l,a: OutreachAgent(b,l,a),
    "sales":           lambda b,l,a: SalesAgent(b,l,a),
    "sales_ops":       lambda b,l,a: SalesOpsAgent(b,l,a),
    "small_biz_expert":lambda b,l,a: SmallBizExpertAgent(b,l,a),
    "research":        lambda b,l,a: ResearchAgent(b,l,a),
    "engineer":        lambda b,l,a: EngineerAgent(b,l,a),
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log_event("system", "thought", "Agent team starting up - 15 agents loading...")
    log_event("system", "thought", f"Katy's brief loaded ({len(KATY_BRIEF)} chars)")
    asyncio.create_task(scheduler.start())
    log_event("system", "thought", "Proactive scheduler activated")
    yield
    scheduler.stop()

app = FastAPI(title="Katy Agent Team - 15 Agents", lifespan=lifespan)
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
            return FileResponse(str(candidate), media_type="text/html")
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
    log_event("katy", "message", message)
    handler = make_task_handler()
    coordinator = CoordinatorAgent(KATY_BRIEF, log_event, request_approval,
                                   dispatch_fn=handler.dispatch)
    response = await coordinator.handle_message(message)
    log_event("coordinator", "message", response[:400])
    return {"response": response}

@app.post("/task")
async def run_task(body: dict):
    task = body.get("task", "")
    agent_name = body.get("agent", "coordinator")
    log_event(agent_name, "thought", f"Starting: {task}")

    if agent_name == "coordinator":
        handler = make_task_handler()
        agent = CoordinatorAgent(KATY_BRIEF, log_event, request_approval,
                                 dispatch_fn=handler.dispatch)
    else:
        factory = AGENT_MAP.get(agent_name)
        if not factory:
            return {"error": f"Unknown agent: {agent_name}"}
        agent = factory(KATY_BRIEF, log_event, request_approval)

    result = await agent.run(task)
    log_event(agent_name, "result", result[:300])
    return {"result": result}

@app.get("/status")
def get_status():
    mem = get_memory_summary()
    return {"online": True, "agents": len(AGENT_MAP), "events_logged": len(event_stream),
            "pending_approvals": len([a for a in approval_queue if a["status"]=="pending"]),
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
    niche = body.get("niche", "local businesses")
    location = body.get("location", "United States")
    limit = body.get("limit", 15)

    task = f"Find {niche} in {location} with missing or incomplete Google Business Profiles. Scan up to {limit} businesses."
    log_event("task_handler", "action", f"GBP pipeline: {niche} in {location}")

    handler = make_task_handler()
    results = await handler.dispatch(
        ["gbp_scout", "gbp_researcher", "outreach"],
        task
    )
    return {"results": results, "niche": niche, "location": location}


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
    prospect_data = {}
    if prospect_phone:
        all_prospects = get_prospects()
        clean = prospect_phone.replace("+1","").replace("-","").replace(" ","").replace("(","").replace(")","")
        prospect_data = next((p for p in all_prospects if clean in str(p.get("phone","")).replace("-","").replace(" ","")), {})

    result = await make_call(
        prospect_phone=prospect_phone,
        prospect_name=body.get("prospect_name") or prospect_data.get("owner_name") or prospect_data.get("business_name", "there"),
        business_name=body.get("business_name") or prospect_data.get("business_name", ""),
        gbp_condition=body.get("gbp_condition") or prospect_data.get("gbp_condition", "INCOMPLETE_PROFILE"),
        issues=body.get("issues") or prospect_data.get("issues", []),
        business_type=body.get("business_type") or prospect_data.get("niche", ""),
        city=body.get("city") or prospect_data.get("location", ""),
        website=prospect_data.get("website", ""),
        description=prospect_data.get("description", ""),
        years_in_business=prospect_data.get("years_in_business", ""),
        services=prospect_data.get("services", ""),
        rating=prospect_data.get("rating", ""),
        review_count=prospect_data.get("review_count", ""),
        extra_intel=prospect_data.get("extra_intel", ""),
        assistant_id=body.get("assistant_id", os.getenv("VAPI_ASSISTANT_ID", "")),
        phone_number_id=body.get("phone_number_id", os.getenv("VAPI_PHONE_NUMBER_ID", "")),
    )
    log_event("vapi", "action", f"Call triggered to {body.get('business_name')} — {result.get('id', 'error')}")
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
    match = next((p for p in prospects if p.get("phone", "").replace("-","").replace(" ","") in phone.replace("-","").replace(" ","")), None)
    if match:
        return {
            "result": json.dumps({
                "business_name": match.get("business_name", ""),
                "owner_name": match.get("owner_name", "there"),
                "city": match.get("location", ""),
                "business_type": match.get("niche", "business"),
                "gbp_condition": match.get("gbp_condition", "INCOMPLETE_PROFILE"),
                "issues": match.get("issues", []),
                "missing_items": ", ".join(match.get("issues", [])[:3]),
            })
        }
    return {"result": json.dumps({"owner_name": "there", "business_name": "your business"})}


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
            update_prospect(
                business_name=match["business_name"],
                location=match.get("location",""),
                pipeline_stage="callback_scheduled",
                extra={
                    "callback_time": callback_time,
                    "callback_reason": reason,
                }
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
            update_prospect(
                business_name=match["business_name"],
                location=match.get("location",""),
                pipeline_stage=outcome,
                extra={
                    "call_outcome": outcome,
                    "temperature": temperature,
                    "call_notes": notes,
                    "objections_raised": objections,
                    "last_called": __import__("datetime").datetime.utcnow().isoformat(),
                }
            )

        log_event("vapi", "action", f"Call notes saved: {business_name} — {outcome} ({temperature}) — {notes[:80]}")
        return {"result": "Notes saved successfully."}
    except Exception as e:
        return {"result": f"Notes saved. ({e})"}


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
                update_prospect(
                    business_name=match["business_name"],
                    location=match.get("location",""),
                    pipeline_stage=structured.get("outcome", ended_reason),
                    extra={
                        "call_summary": summary,
                        "call_outcome": structured.get("outcome", ""),
                        "temperature": structured.get("temperature", ""),
                        "callback_time": structured.get("callback_time", ""),
                        "objections": structured.get("objections", []),
                        "key_quote": structured.get("key_quote", ""),
                        "recording_url": recording_url,
                        "last_called": __import__("datetime").datetime.utcnow().isoformat(),
                    }
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

    assistant = await create_assistant(phone_number_id, katy_phone)
    assistant_id = assistant.get("id", "")

    log_event("vapi", "action", f"Assistant created: {assistant_id}")
    return {
        "assistant_id": assistant_id,
        "phone_number_id": phone_number_id,
        "next_step": f"Add to .env: VAPI_ASSISTANT_ID={assistant_id} and VAPI_PHONE_NUMBER_ID={phone_number_id}"
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)