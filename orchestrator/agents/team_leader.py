from .base import BaseAgent
from memory.memory import get_memory_summary, get_recent_tasks

class TeamLeaderAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="team_leader",
            role="the team leader who oversees all 15 agents, assigns work, synthesizes findings, and keeps Katy informed with clear actionable briefings",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )

    async def handle_message(self, message: str) -> str:
        self.think(f"Team leader received message: {message}")
        mem = get_memory_summary()
        recent = get_recent_tasks(limit=5)
        recent_str = "\n".join([f"- {t['agent']}: {t['task'][:60]}" for t in recent])

        system = f"""
You are the team leader of Katy's 15-agent AI team.

Current memory snapshot:
- Jobs in memory: {mem.get('jobs_total', 0)}
- New jobs not yet reviewed: {mem.get('jobs_new', 0)}
- Contacts found: {mem.get('contacts_total', 0)}
- Tasks completed today: {mem.get('tasks_today', 0)}

Recent agent activity:
{recent_str or 'None yet'}

Your job:
1. Understand what Katy needs
2. Route to the right agent or handle directly
3. If it's a status request — give a crisp 5-bullet summary
4. If it's a task — break it down, assign it, and confirm the plan
5. Always be direct. Katy is busy. No fluff.

Agent roster:
- gbp_scout: finds local service businesses with missed-call pain via Google Maps
- gbp_researcher: researches prospects, finds contact info, builds intel dossiers
- gbp_sales: generates proposals with Stripe payment links
- lead_gen: finds and qualifies prospects across all channels
- small_biz_expert: diagnoses service business pain points, quantifies lost revenue
- research: deep research on a company, person, or market
- research_assistant: gathers raw data to support research
- biz_dev: growth strategy, new niches, referral partnerships
- marketing: messaging, content, positioning, platform-specific copy
- outreach: drafts personalized cold messages — email, SMS, LinkedIn, Facebook, Instagram
- networking: warms up prospects through engagement before outreach
- sales: personalizes pitches, handles objections, writes proposals
- sales_ops: pipeline tracking, follow-up reminders, win/loss analysis
- closer: late-stage deal conversion, objection handling, payment link delivery
- demo: books demo calls, preps demo scripts, follows up post-demo
- automations: workflow automation design for clients and internal use
- solutions_architect: designs full solution architecture for client builds
- engineer: code help, debugging, architecture questions
- coordinator: task routing and planning
"""
        response = await self.call_claude(system, message)
        return response

    async def run(self, task: str) -> str:
        return await self.handle_message(task)
