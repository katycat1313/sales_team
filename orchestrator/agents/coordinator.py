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
- research: deep research on companies, markets, people, opportunities
- research_assistant: gathering raw data to support research
- small_business_expert: small business strategy, how to sell to SMBs
- biz_dev: finding new business opportunities and revenue streams
- lead_gen: finding and qualifying prospects and leads
- marketing: messaging, content, positioning, LinkedIn posts
- automations: designing workflow automations (n8n, Zapier, internal)
- solutions_architect: designing and planning solutions to identified problems
- sales_specialist: closing deals, writing proposals, handling objections
- sales_ops: tracking the pipeline, follow-ups, deal status
- interview_coach: interview and sales pitch practice sessions
- job_seeker: finding jobs, managing applications
- assistant_job_seeker: supporting job search, monitoring boards, follow-ups
- resume_builder: tailoring resume and cover letter per role
- networking: growing Katy's professional network on LinkedIn
- scout: quick job board searches
- outreach: drafting cold emails and DMs
- engineer: debugging code, technical help, architecture advice
- coach: general career coaching and guidance

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
