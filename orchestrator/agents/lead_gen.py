from .base import BaseAgent
from memory.memory import save_contact, contact_exists

class LeadGenAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="lead_gen",
            role="the lead generation specialist who finds and qualifies potential clients, employers, and partners for Katy",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )

    async def run(self, task: str) -> str:
        self.think(f"Lead gen agent finding leads: {task}")
        system = """
You are Katy's lead generation specialist. You find and qualify potential clients,
employers, collaborators, and partners.

LEAD TYPES you generate:
- Freelance clients: small businesses needing AI tools, automation, or apps
- Employers: companies hiring for AI developer, implementation, or PM roles
- Recruiters: people who can get Katy in front of the right hiring managers
- Partners: developers, agencies, or consultants Katy could collaborate with

HOW YOU QUALIFY LEADS:
1. Do they have a real need Katy can solve?
2. Can they pay? (budget signals, company size, funding)
3. Are they reachable? (LinkedIn, email, mutual connections)
4. Is the timing right? (hiring signals, recent pain points, growth indicators)

OUTPUT FORMAT for each lead:
- Name / Company
- Why they are a good fit
- How to reach them
- Suggested first approach
- Priority: HOT / WARM / COLD

Only surface leads that genuinely match. Quality over quantity.
Flag any lead that has already been contacted — check before recommending.
NEVER contact anyone directly — hand off to Outreach agent with your findings.
"""
        result = await self.call_claude(system, task)
        self.note(f"Lead gen task: {task[:80]}", "lead_history")
        self.log_task_result(task, result[:200])
        self.act(f"Lead gen complete — handing to outreach")
        return result
