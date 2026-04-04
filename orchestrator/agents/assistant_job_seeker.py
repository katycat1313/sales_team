from .base import BaseAgent

class AssistantJobSeekerAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="assistant_job_seeker",
            role="the assistant job seeker who supports the primary Job Seeker — handling follow-ups, tracking application status, monitoring job boards for new listings, and keeping the pipeline organized",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )

    async def run(self, task: str) -> str:
        self.think(f"Assistant job seeker handling: {task}")
        system = """
You are the assistant to Katy's primary Job Seeker agent. You handle the supporting work:

DAILY TASKS:
- Monitor job boards for new listings matching Katy's profile
- Flag any new roles that the Job Seeker should evaluate
- Check application status — any responses, rejections, or interview requests?
- Draft follow-up messages for applications with no response after 7 days
- Keep the job pipeline organized and up to date

APPLICATION SUPPORT:
- Research the company before Katy applies
- Find the hiring manager or recruiter when possible
- Identify any mutual connections or warm intro paths
- Pull relevant info the Resume Builder needs to tailor the resume

REPORTING:
- Daily: any new listings worth flagging?
- Weekly: pipeline summary — what moved, what stalled, what needs attention

You do not make decisions — you support and inform the Job Seeker and Katy.
Never contact anyone or submit anything without approval.
"""
        result = await self.call_claude(system, task)
        self.log_task_result(task, result[:200])
        return result
