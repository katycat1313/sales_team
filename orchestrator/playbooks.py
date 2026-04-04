from typing import Any, Callable

from memory.memory import (
    get_contacts,
    get_memory_summary,
    get_prospects,
    get_recent_tasks,
)


PLAYBOOKS = {
    "client-pipeline":   {"title": "Client Pipeline — Find & Pitch"},
    "complaints-scan":   {"title": "Complaints Scan — Find Businesses Losing Calls"},
    "linkedin-outreach": {"title": "LinkedIn Outreach — Find & DM"},
    "prospect-funnel":   {"title": "Prospect Funnel — Nurture to Demo"},
    "target-company":    {"title": "Target a Specific Company"},
    "automation-audit":  {"title": "Automation Audit"},
    "weekly-debrief":    {"title": "Weekly Debrief"},
    "demo-to-close":     {"title": "Demo to Close"},
}


class PlaybookRunner:
    def __init__(self, task_handler, log_event, get_runtime_context: Callable[[], dict] | None = None):
        self.task_handler = task_handler
        self.log_event = log_event
        self.get_runtime_context = get_runtime_context or (lambda: {})

    def list_playbooks(self) -> list[dict[str, str]]:
        return [
            {"id": playbook_id, "title": meta["title"]}
            for playbook_id, meta in PLAYBOOKS.items()
        ]

    async def run(self, playbook_id: str, body: dict | None = None) -> dict[str, Any]:
        payload = body or {}
        runners = {
            "client-pipeline":  self._run_client_pipeline,
            "complaints-scan":  self._run_complaints_scan,
            "linkedin-outreach": self._run_linkedin_outreach,
            "prospect-funnel":  self._run_prospect_funnel,
            "target-company":   self._run_target_company,
            "automation-audit": self._run_automation_audit,
            "weekly-debrief":   self._run_weekly_debrief,
            "demo-to-close":    self._run_demo_to_close,
        }
        runner = runners.get(playbook_id)
        if not runner:
            raise ValueError(f"Unknown playbook: {playbook_id}")
        return await runner(payload)

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _run_steps(self, playbook_id: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
        title = PLAYBOOKS[playbook_id]["title"]
        self.log_event("playbook", "action", f"Launching {title}")
        outputs = []
        for step in steps:
            task_factory = step["task"]
            task = task_factory(outputs) if callable(task_factory) else task_factory
            result = await self.task_handler.run_agent(step["agent"], task)
            outputs.append({"agent": step["agent"], "task": task, "result": result})
        summary = self._build_summary(title, outputs)
        self.log_event("playbook", "result", summary[:400])
        return {"playbook": playbook_id, "title": title, "summary": summary, "steps": outputs}

    def _runtime(self) -> dict[str, Any]:
        try:
            data = self.get_runtime_context() or {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _top_prospects(self, limit: int = 5) -> list[dict[str, Any]]:
        hot = get_prospects(priority="HOT", limit=limit)
        if len(hot) >= limit:
            return hot[:limit]
        warm = get_prospects(priority="WARM", limit=limit - len(hot))
        return (hot + warm)[:limit]

    def _format_prospects(self, prospects: list[dict[str, Any]]) -> str:
        if not prospects:
            return "None in memory."
        lines = []
        for p in prospects:
            issues = str(p.get("gbp_issues") or p.get("research_notes") or p.get("notes") or "").replace("\n", " ").strip()
            lines.append(
                f"- {p.get('business_name','?')} | {p.get('location','?')} | {p.get('niche','?')} "
                f"| priority={p.get('priority','WARM')} | phone={p.get('phone','')} "
                f"| score={p.get('buyer_intent_score') or p.get('gbp_score','')} "
                f"| issues={issues[:120] or 'not captured'}"
            )
        return "\n".join(lines)

    def _format_contacts(self, contacts: list[dict[str, Any]]) -> str:
        if not contacts:
            return "None in memory."
        return "\n".join(
            f"- {c.get('name','?')} | {c.get('company','?')} | {c.get('title','?')} | {c.get('platform','?')}"
            for c in contacts[:8]
        )

    def _results_context(self, outputs: list[dict[str, Any]]) -> str:
        if not outputs:
            return "No prior agent output yet."
        return "\n\n".join(f"[{item['agent']}]\n{item['result']}" for item in outputs)

    def _build_summary(self, title: str, outputs: list[dict[str, Any]]) -> str:
        if not outputs:
            return f"{title} finished with no agent output."
        last = outputs[-1]["result"].strip().replace("\n", " ")
        return f"{title} completed via {', '.join(item['agent'] for item in outputs)}. {last[:320]}"

    # ── Playbooks ─────────────────────────────────────────────────────────────

    async def _run_complaints_scan(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Mine Yelp and Google reviews to find businesses where customers already
        complain about unanswered calls, voicemail, and slow response.
        These are the hottest possible prospects — the problem is already documented publicly.
        """
        niche    = str(payload.get("niche", "plumbers")).strip()
        location = str(payload.get("location", "Charleston WV")).strip()

        steps = [
            {
                "agent": "gbp_scout",
                "task": (
                    f"Use the review_miner tool to scan Yelp and Google reviews for {niche} businesses "
                    f"in {location} where customers complain about unanswered calls, voicemail, long wait times, "
                    f"or slow response. Call scan_for_call_complaints('{niche}', '{location}'). "
                    f"Return every business found with their complaint score, the actual complaint quotes from "
                    f"reviews, phone number, and why they are a perfect fit for Missed-Call-Revenue. "
                    f"Real data only — no invented businesses."
                ),
            },
            {
                "agent": "small_biz_expert",
                "task": lambda outputs: (
                    "Using the complaint scan results below, calculate the real revenue each business is "
                    "losing due to missed calls. Use their niche to estimate average job value and the "
                    "number of calls they're likely missing per week. Quote the specific complaints from "
                    "their reviews — that language is our pitch hook. Rank them by urgency.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
            {
                "agent": "sales",
                "task": lambda outputs: (
                    "Write a cold pitch for each business below. "
                    "LEAD WITH THEIR OWN REVIEW LANGUAGE — quote what their customer said, then show how "
                    "Eric solves exactly that. These businesses have public proof of the problem. "
                    "Make every pitch feel like you read their reviews because you did.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
            {
                "agent": "outreach",
                "task": lambda outputs: (
                    "Turn the pitches below into ready-to-send outreach drafts. "
                    "These prospects were found via review complaints — the opening line should reference "
                    "something a real customer said about them. "
                    "For each business produce: (1) EMAIL subject + body, (2) SMS if phone available. "
                    "Queue all for Katy's approval. No placeholders.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
        ]
        return await self._run_steps("complaints-scan", steps)

    async def _run_linkedin_outreach(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Find service business owners on LinkedIn → research them → DM them as Katy.
        Requires LinkedIn session saved via /browser/login/linkedin.
        """
        niche    = str(payload.get("niche", "plumbing OR HVAC OR electrician")).strip()
        location = str(payload.get("location", "")).strip()

        steps = [
            {
                "agent": "gbp_researcher",
                "task": (
                    f"Search LinkedIn for service business owners or operators in the {niche} niche"
                    + (f" near {location}" if location else "")
                    + ". Use the linkedin_search_businesses tool. "
                    "For each result, find their business name, their role, and any public signals "
                    "that suggest they handle a lot of calls — phone service, contracting, home services, etc. "
                    "Return profile URLs, names, business names, and a brief note on why they're a good fit. "
                    "Real profiles only."
                ),
            },
            {
                "agent": "small_biz_expert",
                "task": lambda outputs: (
                    "Using the LinkedIn profiles found below, identify the top 5 best prospects for "
                    "Katy's AI answering service. For each one, write one specific hook — what pain point "
                    "do they have that the service solves? Reference what you can see from their profile.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
            {
                "agent": "sales",
                "task": lambda outputs: (
                    "Write a short LinkedIn DM pitch for each of the top prospects below. "
                    "Under 300 characters. Lead with something specific you noticed about their business. "
                    "One clear ask at the end. No fluff, no templates. Sound like Katy wrote it personally.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
            {
                "agent": "outreach",
                "task": lambda outputs: (
                    "Format the LinkedIn DMs below into final outreach drafts. "
                    "Platform: linkedin. These will be sent from Katy's LinkedIn profile. "
                    "Also write an email version for each prospect if an email can be inferred. "
                    "Queue all for Katy's approval before sending.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
        ]
        return await self._run_steps("linkedin-outreach", steps)

    async def _run_client_pipeline(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Full top-of-funnel: scan Google Maps for real service businesses →
        research each one → diagnose pain → craft personalized pitch → queue outreach.
        """
        niche = str(payload.get("niche", "plumbers")).strip()
        location = str(payload.get("location", "Charleston WV")).strip()
        steps = [
            {
                "agent": "gbp_scout",
                "task": (
                    f"Scan Google Maps for {niche} businesses in {location}. Find 8 real service businesses "
                    f"that show signs of missed-call pain: no website, low reviews, unclaimed profile, or gaps in "
                    f"online presence. Return business name, phone, address, website, and specific issues found. "
                    f"Real data only — no invented businesses."
                ),
            },
            {
                "agent": "gbp_researcher",
                "task": lambda outputs: (
                    "For each business found by the scout below, research deeper: find the owner name if possible, "
                    "confirm the phone number, check their website quality, read their reviews for pain signals, "
                    "and score each one by how urgently they need an AI answering service. Rank them HOT / WARM / COLD.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
            {
                "agent": "small_biz_expert",
                "task": lambda outputs: (
                    "Using the researched prospects below, identify the single most compelling pain point for each "
                    "business and the best outreach hook. Be specific — reference their actual reviews, missing info, "
                    "or call handling gap.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
            {
                "agent": "sales",
                "task": lambda outputs: (
                    "Write a short, personalized cold pitch for each HOT and WARM business below. "
                    "Lead with their specific pain. Mention one concrete outcome of using Katy's AI answering service. "
                    "No generic copy. Each pitch must feel written for that business only.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
            {
                "agent": "outreach",
                "task": lambda outputs: (
                    "Turn the pitches below into ready-to-send outreach drafts. "
                    "These prospects were found via Google Maps. For each business produce: "
                    "(1) an EMAIL — subject + body, "
                    "(2) an SMS opener (under 160 chars) if a phone number is available, "
                    "(3) note the platform as 'google_maps' so the right channel is used. "
                    "Queue all drafts for Katy's approval before sending. No placeholders.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
        ]
        return await self._run_steps("client-pipeline", steps)

    async def _run_prospect_funnel(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """
        Takes existing prospects already in memory and moves them forward:
        follow up with those who haven't replied, send demo to warm ones,
        push hot ones toward a decision.
        """
        prospects = self._top_prospects(limit=8)
        prospect_context = self._format_prospects(prospects)
        contacts = self._format_contacts(get_contacts())

        if not prospects:
            return {
                "playbook": "prospect-funnel",
                "title": PLAYBOOKS["prospect-funnel"]["title"],
                "summary": "No prospects in memory. Run client-pipeline first to fill the funnel.",
                "steps": [],
            }

        steps = [
            {
                "agent": "sales_ops",
                "task": (
                    "Review the current prospect pipeline below. Identify who needs a follow-up, who is warm enough "
                    "for a demo invitation, and who is stalled. Give a clear recommended next action for each.\n\n"
                    f"Prospects:\n{prospect_context}\n\nContacts:\n{contacts}"
                ),
            },
            {
                "agent": "sales",
                "task": lambda outputs: (
                    "Based on the pipeline review below, write the follow-up message for each prospect that needs one. "
                    "For warm prospects, write a demo invitation. For hot prospects, write a close message with a "
                    "clear call to action. Personalize every message to that specific business.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
            {
                "agent": "outreach",
                "task": lambda outputs: (
                    "Format the follow-up messages below into ready-to-send drafts via email or SMS as appropriate. "
                    "Include demo link where relevant. Queue all for Katy's approval before sending.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
        ]
        return await self._run_steps("prospect-funnel", steps)

    async def _run_demo_to_close(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Takes a prospect who has seen the demo and is evaluating.
        Builds a personalized close strategy and sends payment link when ready.
        """
        business_name = str(payload.get("business_name", "")).strip()
        prospects = self._top_prospects(limit=8)
        if business_name:
            match = next((p for p in prospects if business_name.lower() in p.get("business_name", "").lower()), None)
            target = match or {}
        else:
            target = next((p for p in prospects if str(p.get("buyer_intent_score", 0)) >= "7"), {})

        if not target:
            return {
                "playbook": "demo-to-close",
                "title": PLAYBOOKS["demo-to-close"]["title"],
                "summary": "No qualifying prospect found. Specify business_name or run prospect-funnel first.",
                "steps": [],
            }

        biz = target.get("business_name", business_name)
        context = self._format_prospects([target])

        steps = [
            {
                "agent": "research",
                "task": (
                    f"Research {biz} deeply right now. Find their current call handling setup, how many services they offer, "
                    f"what their reviews say about responsiveness, and any recent news. This intel will be used to close a sale.\n\n"
                    f"What we know so far:\n{context}"
                ),
            },
            {
                "agent": "small_biz_expert",
                "task": lambda outputs: (
                    f"Using the research below about {biz}, identify the strongest ROI argument for why they need "
                    f"Katy's AI answering service right now. Quantify the missed revenue if possible.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
            {
                "agent": "sales",
                "task": lambda outputs: (
                    f"Write a closing message for {biz}. They've seen the demo. Address their specific hesitation, "
                    f"reinforce the ROI, and end with a direct call to action — either reply to confirm the tier or "
                    f"a payment link will be sent. Recommend the right tier based on their business size.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
            {
                "agent": "outreach",
                "task": lambda outputs: (
                    f"Turn the closing message below into a final outreach draft for {biz} — email + SMS version. "
                    f"Queue for Katy's approval. If approved, the payment link goes out immediately.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
        ]
        return await self._run_steps("demo-to-close", steps)

    async def _run_target_company(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Deep research + personalized pitch for one specific business."""
        company = str(payload.get("company", "")).strip()
        if not company:
            raise ValueError("company name is required")

        steps = [
            {
                "agent": "gbp_researcher",
                "task": (
                    f"Research {company} in depth: website, reviews, Google Business Profile status, "
                    f"call handling signals, owner name if findable, social presence, and any visible pain points "
                    f"around missed calls or slow lead response. Return concrete facts only."
                ),
            },
            {
                "agent": "small_biz_expert",
                "task": lambda outputs: (
                    f"Using the research below about {company}, pinpoint the top 2 pain points Katy's AI answering "
                    f"service solves for them specifically. Identify the best outreach hook.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
            {
                "agent": "sales",
                "task": lambda outputs: (
                    f"Write a personalized pitch for {company}. Reference real facts from the research. "
                    f"Lead with their pain, present the solution, and end with a clear next step.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
            {
                "agent": "outreach",
                "task": lambda outputs: (
                    f"Turn the pitch below into approval-ready outreach for {company}: cold email + SMS version. "
                    f"Queue for Katy's review before sending.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
        ]
        return await self._run_steps("target-company", steps)

    async def _run_automation_audit(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """Identifies automation gaps in prospect businesses — doubles as upsell intel."""
        prospects = self._top_prospects(limit=5)
        prospect_context = self._format_prospects(prospects)
        steps = [
            {
                "agent": "automations",
                "task": (
                    "For each real business below, identify 3 specific workflow pain points that an AI answering "
                    "service would fix. Focus on missed calls, slow lead response, after-hours gaps, and manual "
                    "follow-up. Be specific to each business.\n\n"
                    f"Prospects:\n{prospect_context}"
                ),
            },
            {
                "agent": "solutions_architect",
                "task": lambda outputs: (
                    "Turn the automation findings below into a solution summary per business. Include which service "
                    "tier fits best (Starter $97/mo, Standard $197/mo, Pro $297/mo) and why.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
        ]
        return await self._run_steps("automation-audit", steps)

    async def _run_weekly_debrief(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """Sales team status: what happened, what's pending, what to do next."""
        memory_summary = get_memory_summary()
        recent_tasks = "\n".join(
            f"- {t.get('agent','?')}: {str(t.get('task',''))[:110]}"
            for t in get_recent_tasks(limit=10)
        ) or "None recorded."
        prospects = self._format_prospects(self._top_prospects(limit=5))
        runtime = self._runtime()
        pending_approvals = runtime.get("pending_approvals", 0)
        scheduled = runtime.get("scheduled_events") or []
        scheduled_text = "\n".join(
            f"- {e.get('agent','?')} @ {e.get('run_at','?')}: {str(e.get('task',''))[:100]}"
            for e in scheduled[:5]
        ) or "None scheduled."

        steps = [
            {
                "agent": "team_leader",
                "task": (
                    "Generate the weekly sales debrief. Be direct and specific — what was accomplished, "
                    "what is stalled, what needs Katy's attention right now, and the top 3 priorities for the week ahead.\n\n"
                    f"Memory: {memory_summary}\n"
                    f"Pending approvals: {pending_approvals}\n"
                    f"Scheduled:\n{scheduled_text}\n"
                    f"Top prospects:\n{prospects}\n"
                    f"Recent activity:\n{recent_tasks}"
                ),
            }
        ]
        return await self._run_steps("weekly-debrief", steps)
