from typing import Any, Callable

from memory.memory import (
    get_contacts,
    get_jobs,
    get_memory_summary,
    get_prospects,
    get_recent_tasks,
)


PLAYBOOKS = {
    "job-hunt": {"title": "Full Job Hunt"},
    "client-pipeline": {"title": "Client Pipeline"},
    "interview-ready": {"title": "Interview Ready"},
    "automation-audit": {"title": "Automation Audit"},
    "weekly-debrief": {"title": "Weekly Debrief"},
    "target-company": {"title": "Target a Company"},
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
            "job-hunt": self._run_job_hunt,
            "client-pipeline": self._run_client_pipeline,
            "interview-ready": self._run_interview_ready,
            "automation-audit": self._run_automation_audit,
            "weekly-debrief": self._run_weekly_debrief,
            "target-company": self._run_target_company,
        }
        runner = runners.get(playbook_id)
        if not runner:
            raise ValueError(f"Unknown playbook: {playbook_id}")
        return await runner(payload)

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
        return {
            "playbook": playbook_id,
            "title": title,
            "summary": summary,
            "steps": outputs,
        }

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
        for prospect in prospects:
            issues = prospect.get("gbp_issues") or prospect.get("research_notes") or prospect.get("notes") or ""
            issues_text = str(issues).replace("\n", " ").strip()
            if len(issues_text) > 140:
                issues_text = issues_text[:137] + "..."
            lines.append(
                "- {business} | {location} | {niche} | priority={priority} | issues={issues}".format(
                    business=prospect.get("business_name", "Unknown business"),
                    location=prospect.get("location", "Unknown location"),
                    niche=prospect.get("niche", "unknown niche"),
                    priority=prospect.get("priority", "WARM"),
                    issues=issues_text or "not captured yet",
                )
            )
        return "\n".join(lines)

    def _format_jobs(self, jobs: list[dict[str, Any]]) -> str:
        if not jobs:
            return "None in memory."
        return "\n".join(
            f"- {job.get('title', 'Unknown role')} | {job.get('company', 'Unknown company')} | {job.get('location', 'Unknown location')} | {job.get('salary', 'salary n/a')}"
            for job in jobs[:8]
        )

    def _format_contacts(self, contacts: list[dict[str, Any]]) -> str:
        if not contacts:
            return "None in memory."
        return "\n".join(
            f"- {contact.get('name', 'Unknown')} | {contact.get('company', 'Unknown company')} | {contact.get('title', 'title n/a')} | {contact.get('platform', 'platform n/a')}"
            for contact in contacts[:8]
        )

    def _format_recent_tasks(self, tasks: list[dict[str, Any]]) -> str:
        if not tasks:
            return "None recorded."
        return "\n".join(
            f"- {task.get('agent', 'unknown')}: {str(task.get('task', ''))[:110]}"
            for task in tasks[:10]
        )

    def _results_context(self, outputs: list[dict[str, Any]]) -> str:
        if not outputs:
            return "No prior agent output yet."
        return "\n\n".join(
            f"[{item['agent']}]\n{item['result']}" for item in outputs
        )

    def _build_summary(self, title: str, outputs: list[dict[str, Any]]) -> str:
        if not outputs:
            return f"{title} finished with no agent output."
        last = outputs[-1]["result"].strip().replace("\n", " ")
        if len(last) > 320:
            last = last[:317] + "..."
        return f"{title} completed via {', '.join(item['agent'] for item in outputs)}. {last}"

    async def _run_job_hunt(self, _payload: dict[str, Any]) -> dict[str, Any]:
        known_jobs = self._format_jobs(get_jobs())
        known_contacts = self._format_contacts(get_contacts())
        steps = [
            {
                "agent": "scout",
                "task": (
                    "Run the Full Job Hunt playbook for Katy Casto. Find 8 NEW roles posted recently that match her real background: "
                    "AI application development, React, TypeScript, JavaScript, Python, Supabase, Claude API, Gemini, Docker, "
                    "and 10+ years of digital marketing. Prioritize remote roles or roles near Charleston/Belle WV paying at least "
                    "$35/hr or $50k salary. Return concrete listings only, no generic advice. Existing jobs in memory:\n"
                    f"{known_jobs}"
                ),
            },
            {
                "agent": "job_seeker",
                "task": lambda outputs: (
                    "Review the scout findings below and choose the top 5 opportunities by fit, pay, and interview likelihood. "
                    "For each one, explain the exact angle Katy should lead with in an application.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
            {
                "agent": "resume_builder",
                "task": lambda outputs: (
                    "Using the prioritized roles below, draft tailored resume bullet updates and cover-letter angles for the top 3 roles. "
                    "Do not invent experience. Queue any approval needed before submission.\n\n"
                    f"Existing recruiter/contact memory:\n{known_contacts}\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
            {
                "agent": "networking",
                "task": lambda outputs: (
                    "Using the top roles and tailored application angles below, draft warm recruiter or hiring-manager outreach messages "
                    "for the top 3 roles. Require approval before sending anything.\n\n"
                    f"Existing contact memory:\n{known_contacts}\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
        ]
        return await self._run_steps("job-hunt", steps)

    async def _run_client_pipeline(self, _payload: dict[str, Any]) -> dict[str, Any]:
        prospects = self._top_prospects(limit=5)
        steps = []

        if not prospects:
            steps.extend(
                [
                    {
                        "agent": "lead_gen",
                        "task": (
                            "Run the Client Pipeline playbook. There are no HOT or WARM prospects in memory, so find 5 real local service "
                            "businesses likely to miss inbound calls and need faster lead response. Return only real businesses with clear sales opportunity and priority scores."
                        ),
                    },
                    {
                        "agent": "research_assistant",
                        "task": lambda outputs: (
                            "Enrich the newly found prospects below with owner/contact details and concrete proof of missed-call pain points so the "
                            "next agents can pitch real businesses for the Missed-Call-Revenue service.\n\n"
                            f"{self._results_context(outputs)}"
                        ),
                    },
                ]
            )

        prospect_context = self._format_prospects(prospects)
        steps.extend(
            [
                {
                    "agent": "small_biz_expert",
                    "task": lambda outputs: (
                        "Run the Client Pipeline playbook. Use only real prospects. Diagnose the top 3 pain points per business and explain "
                        "the best outreach hook for each.\n\n"
                        f"Prospects from memory:\n{prospect_context}\n\n"
                        f"Prior outputs:\n{self._results_context(outputs)}"
                    ),
                },
                {
                    "agent": "solutions_architect",
                    "task": lambda outputs: (
                        "Design the fix package for each real client prospect below, including scope, implementation approach, and realistic "
                        "monthly pricing.\n\n"
                        f"{self._results_context(outputs)}"
                    ),
                },
                {
                    "agent": "sales",
                    "task": lambda outputs: (
                        "Write a concise, personalized pitch for each real business below. The pitch must call out one specific issue and "
                        "connect it to Katy's solution.\n\n"
                        f"{self._results_context(outputs)}"
                    ),
                },
                {
                    "agent": "outreach",
                    "task": lambda outputs: (
                        "Turn the sales pitches below into outreach drafts queued for Katy's approval. Use real business names and avoid "
                        "placeholder copy.\n\n"
                        f"{self._results_context(outputs)}"
                    ),
                },
            ]
        )
        return await self._run_steps("client-pipeline", steps)

    async def _run_interview_ready(self, _payload: dict[str, Any]) -> dict[str, Any]:
        steps = [
            {
                "agent": "coach",
                "task": (
                    "Run the Interview Ready playbook for Katy Casto. Build a prep plan for AI Application Developer and Solutions "
                    "Implementation Specialist roles. Cover technical depth, project walkthroughs, system design, behavioral answers, and "
                    "salary framing based on her real stack and projects."
                ),
            },
            {
                "agent": "interview_coach",
                "task": lambda outputs: (
                    "Use the prep plan below to begin an interview practice session. Ask the strongest first question, provide a model "
                    "answer framework Katy can study, and note what she should emphasize.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
        ]
        return await self._run_steps("interview-ready", steps)

    async def _run_automation_audit(self, _payload: dict[str, Any]) -> dict[str, Any]:
        prospects = self._top_prospects(limit=5)
        prospect_context = self._format_prospects(prospects)
        steps = [
            {
                "agent": "automations",
                "task": (
                    "Run the Automation Audit playbook. Use the real businesses below and identify at least 3 specific workflow pain points "
                    "that can be automated for each.\n\n"
                    f"Real prospects:\n{prospect_context}"
                ),
            },
            {
                "agent": "solutions_architect",
                "task": lambda outputs: (
                    "Turn the automation findings below into a full implementation plan with tools, workflow design, effort estimate, and "
                    "pricing per business.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
        ]
        return await self._run_steps("automation-audit", steps)

    async def _run_weekly_debrief(self, _payload: dict[str, Any]) -> dict[str, Any]:
        memory_summary = get_memory_summary()
        recent_tasks = self._format_recent_tasks(get_recent_tasks(limit=10))
        prospects = self._format_prospects(self._top_prospects(limit=5))
        runtime = self._runtime()
        scheduled = runtime.get("scheduled_events") or []
        pending_approvals = runtime.get("pending_approvals", 0)
        scheduled_text = "\n".join(
            f"- {item.get('agent', 'unknown')} @ {item.get('run_at', 'n/a')} :: {str(item.get('task', ''))[:120]}"
            for item in scheduled[:5]
        ) or "None scheduled."

        steps = [
            {
                "agent": "team_leader",
                "task": (
                    "Generate the Weekly Debrief for Katy using the real system state below. Keep it factual, concise, and action-oriented.\n\n"
                    f"Memory summary: {memory_summary}\n"
                    f"Pending approvals: {pending_approvals}\n"
                    f"Upcoming scheduled events:\n{scheduled_text}\n\n"
                    f"Top prospects:\n{prospects}\n\n"
                    f"Recent agent activity:\n{recent_tasks}"
                ),
            }
        ]
        return await self._run_steps("weekly-debrief", steps)

    async def _run_target_company(self, payload: dict[str, Any]) -> dict[str, Any]:
        company = str(payload.get("company", "")).strip()
        if not company:
            raise ValueError("company is required")

        steps = [
            {
                "agent": "research",
                "task": (
                    f"Run the Target a Company playbook for {company}. Research the company deeply: website, offers, reviews, online "
                    "presence, positioning, and any digital weaknesses. Surface specific facts only."
                ),
            },
            {
                "agent": "small_biz_expert",
                "task": lambda outputs: (
                    f"Using the research below about {company}, diagnose the top 3 business pain points Katy can solve and identify the "
                    "strongest outreach hook.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
            {
                "agent": "sales",
                "task": lambda outputs: (
                    f"Using the research and diagnosis below, craft a concise personalized pitch for {company}. Reference a real issue and "
                    "present a clear next step.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
            {
                "agent": "outreach",
                "task": lambda outputs: (
                    f"Turn the pitch below for {company} into an approval-ready outreach draft Katy can review before sending.\n\n"
                    f"{self._results_context(outputs)}"
                ),
            },
        ]
        return await self._run_steps("target-company", steps)