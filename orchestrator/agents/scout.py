from .base import BaseAgent
from memory.memory import save_job, get_jobs, job_exists

class ScoutAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="scout",
            role="the job search specialist who finds relevant job listings, identifies recruiters, and researches target companies",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )

    async def run(self, task: str) -> str:
        self.think(f"Scout starting search: {task}")

        # Pull what we already know so we don't repeat
        known_jobs = get_jobs()
        known_count = len(known_jobs)
        known_list = ""
        if known_jobs:
            known_list = "\n".join([f"- {j['title']} at {j['company']}" for j in known_jobs[:20]])

        system = f"""
You are Katy's job search specialist. Your job is to:
1. Identify the best job titles for Katy based on her skills
2. Find where those jobs are posted (Wellfound, LinkedIn, Contra, Remote.co)
3. Identify specific recruiters and hiring managers at target companies
4. Research companies to find best-fit opportunities

Match to Katy's actual skills: React, TypeScript, Supabase, Claude API, Gemini, ElevenLabs, Deepgram, Runway
Target: AI startups, SaaS companies, agencies doing AI implementation
Pay range: $35/hr or $50-60k salary minimum

IMPORTANT — You already know about {known_count} jobs. Do NOT suggest these again:
{known_list}

Only surface NEW opportunities Katy hasn't seen yet.

Format each result as:
TITLE | COMPANY | SALARY | LOCATION | WHY IT FITS | WHERE TO APPLY

End with a 1-line summary of what you found.
NEVER apply to anything — draft only, all applications need Katy's approval.
"""
        result = await self.call_claude(system, task)

        # Save findings to memory
        self.remember("last_search", task)
        self.remember("total_searches", str(int(self.recall("total_searches") or 0) + 1))
        self.note(f"Search: {task[:80]} — found results", "search_history")
        self.log_task_result(task, result[:200])
        self.act(f"Scout completed search — {known_count} jobs already in memory")

        return result
