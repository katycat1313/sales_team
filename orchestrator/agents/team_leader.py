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
- research: deep research on any topic
- research_assistant: supports research tasks
- small_biz_expert: diagnoses small business problems
- biz_dev: growth and partnership strategy
- lead_gen: finds and qualifies prospects
- marketing: content, messaging, positioning
- automations: workflow and automation design
- solutions_architect: solution design and implementation planning
- sales: closing deals and pitching
- sales_ops: pipeline tracking and operations
- coach: interview and pitch practice
- job_seeker: finds and applies for jobs
- asst_job_seeker: supports job search
- networking: LinkedIn and relationship building
- scout: job board search (existing)
- outreach: drafts messages (existing)
- engineer: code help (existing)
"""
        response = await self.call_claude(system, message)
        return response

    async def run(self, task: str) -> str:
        return await self.handle_message(task)
