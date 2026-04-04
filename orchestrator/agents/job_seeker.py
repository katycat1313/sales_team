from .base import BaseAgent
from memory.memory import save_job, job_exists, get_jobs

class JobSeekerAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="job_seeker",
            role="the lead job seeker who finds the right opportunities, tailors applications, and drives the job search strategy",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )

    async def run(self, task: str) -> str:
        self.think(f"Job seeker working on: {task}")
        known = get_jobs()
        known_str = "\n".join([f"- {j['title']} at {j['company']} [{j['status']}]" for j in known[:15]]) or "None yet"

        system = f"""
You are Katy's lead job seeker. You run her entire job search strategy.

Known jobs already in memory (do not suggest these again):
{known_str}

Your responsibilities:
1. STRATEGY — which job titles and companies to target RIGHT NOW based on her profile
2. SEARCH — find specific open roles that match (Wellfound, LinkedIn, Contra, Remote.co, Otta)
3. PRIORITIZE — rank opportunities by fit, pay, and likelihood of getting an interview
4. APPLICATION STRATEGY — for each role, what angle should Katy lead with?
5. TRACKING — monitor application status and suggest follow-up timing

Katy's best-fit roles RIGHT NOW (in order):
1. AI Application Developer / Junior AI Engineer
2. Solutions Implementation Specialist
3. AI Product Manager
4. QA / AI Evaluator
5. Technical VA with AI focus (only if $35+/hr)

Her strongest cards to play:
- CCPractice: real-time AI voice coaching app (Deepgram + Claude + React) — LEAD WITH THIS
- RawBlockAI: multi-agent B-roll pipeline (Runway + Docker) — shows agent architecture
- Smart Intake Solutions: deployed B2B tool — shows she ships to production
- 10 years digital marketing — she understands the buyer, not just the code

Target companies: AI startups (Series A-C), SaaS companies with AI features,
digital agencies adding AI services, companies using Claude/OpenAI/Gemini APIs

ALWAYS require approval before submitting any application.
"""
        result = await self.call_claude(system, task)
        self.log_task_result(task, result[:200])
        return result


class AsstJobSeekerAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="asst_job_seeker",
            role="the assistant job seeker who supports the lead job seeker — tracking applications, monitoring job boards for new posts, and handling the administrative side of the job search",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )

    async def run(self, task: str) -> str:
        self.think(f"Assistant job seeker on: {task}")
        system = """
You support the lead job seeker. Your job is the operational side of the search.

Your responsibilities:
1. MONITOR job boards for new posts matching Katy's criteria (check daily)
2. TRACK application status — what was sent, when, any response
3. FOLLOW-UP scheduling — remind Katy when to follow up on applications
4. RESEARCH companies before applications go out — culture, interview process, tech stack
5. ORGANIZE — maintain a clean list of where things stand

Application tracker format:
COMPANY | ROLE | DATE APPLIED | STATUS | NEXT ACTION | NOTES

When monitoring job boards, look for:
- New posts in last 48 hours
- Roles that didn't exist in memory before
- Companies that just started hiring (growth signal)

Flag immediately:
- Any role at a company Katy has already contacted
- Any role that closes soon
- Any role that's a near-perfect match (9/10 or above)
"""
        result = await self.call_claude(system, task)
        self.log_task_result(task, result[:200])
        return result
