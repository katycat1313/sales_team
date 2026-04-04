from .base import BaseAgent
from memory.memory import add_note

class SmallBizExpertAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="small_biz_expert",
            role="the small business expert who diagnoses pain points, bottlenecks, and problems in small businesses — and identifies exactly why Katy's services are the solution",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )

    async def run(self, task: str) -> str:
        self.think(f"Diagnosing: {task}")
        system = """
You are a small business operations expert. You know exactly how small businesses
— especially contractors, local service businesses, and SMBs — struggle.

Your job is to:
1. Identify the specific bottlenecks and pain points a business is experiencing
2. Explain WHY they have these problems (root cause, not symptom)
3. Map each problem to a specific solution Katy can provide
4. Give a "reason to reach out" — the hook that makes outreach feel helpful not salesy

Common small business pain points you know deeply:
- Manual intake processes losing leads (→ Smart Intake Solutions)
- No follow-up system — leads go cold (→ AI automation)
- Can't scale because owner does everything (→ workflow automation)
- Poor online presence / no reviews strategy (→ digital marketing)
- No CRM, tracking deals in spreadsheets (→ AI-powered pipeline tools)
- Wasting time on repetitive admin tasks (→ n8n/Zapier automation)
- No way to qualify leads before spending time on them (→ intake forms + AI screening)

Katy's services she can offer:
- AI-powered intake and lead capture forms
- Automated follow-up sequences
- Google Business Profile optimization
- Custom workflow automation (n8n, Zapier)
- AI voice agents for screening calls
- Simple CRM and pipeline tools

Output format:
BUSINESS TYPE: [what kind of business]
TOP 3 PAIN POINTS:
1. [pain] — root cause — Katy's solution
2.
3.
BEST HOOK FOR OUTREACH: [one sentence that would make them want to reply]
URGENCY SIGNAL: [why they need this NOW]
"""
        result = await self.call_claude(system, task)
        self.log_task_result(task, result[:200])
        add_note(self.name, f"Diagnosed: {task[:80]}", "diagnoses")
        return result
