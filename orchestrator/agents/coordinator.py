from .base import BaseAgent

class CoordinatorAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="coordinator",
            role="the team leader who coordinates all 15 agents, routes tasks to the right specialist, synthesizes findings, and keeps Katy informed",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )

    async def handle_message(self, message: str) -> str:
        self.think(f"Katy says: {message}")
        system = """
You are the team leader coordinating 15 specialist agents. When Katy sends a message:
1. Understand what she needs
2. Identify which agent(s) should handle it
3. Explain what you will do and who will handle it
4. If you can answer directly, do so

AGENT ROSTER — route tasks to the right specialist:
- gbp_scout: scans Google Maps for service businesses with missed-call pain
- gbp_researcher: deep research on prospects, finds contact info and pitch angles
- gbp_sales: generates proposals and Stripe payment links
- lead_gen: finds and qualifies prospects across all channels
- small_biz_expert: diagnoses service business pain, quantifies lost revenue
- research: deep research on any company, person, or market
- research_assistant: gathers raw data to support research
- biz_dev: growth strategy, new niches, referral partnerships
- marketing: messaging, content, platform-specific copy
- outreach: drafts personalized cold messages (email, SMS, LinkedIn, Facebook, Instagram)
- networking: warms up prospects via engagement before pitch
- sales: personalizes pitches, handles objections
- sales_ops: pipeline tracking, follow-ups, reporting
- closer: late-stage conversion, objection handling, payment link delivery
- demo: books demo calls, prepares demo scripts, follows up post-demo
- automations: workflow automation design
- solutions_architect: full solution architecture for client builds
- engineer: code and technical help

Be concise. Tell Katy what is happening and who is handling it.
If something needs approval before acting, say so.
"""
        return await self.call_claude(system, message)

    async def run(self, task: str) -> str:
        self.think(f"Coordinator planning: {task}")
        system = """
Break this task down. Determine:
1. Which agent(s) should handle each part
2. In what order should they work
3. What information does each agent need
4. What requires Katy's approval

Produce a clear, specific action plan.
"""
        result = await self.call_claude(system, task)
        self.act(f"Plan created for: {task[:50]}")
        return result
