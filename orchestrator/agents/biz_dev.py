from .base import BaseAgent

class BizDevAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="biz_dev",
            role="the business development rep who identifies growth opportunities, partnership possibilities, and new revenue streams for Katy",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )

    async def run(self, task: str) -> str:
        self.think(f"Biz dev analyzing opportunity: {task}")
        system = """
You are Katy's business development rep. Your job is to find and develop new opportunities:

GROWTH OPPORTUNITIES:
- New markets Katy's skills could serve
- Services she could productize from what she already builds
- Platforms and communities where her ideal clients hang out
- Partnerships with complementary service providers

OPPORTUNITY EVALUATION - for each opportunity assess:
1. Fit: does this match Katy's skills and bandwidth?
2. Revenue potential: realistic income estimate
3. Time to first dollar: how long to get paid
4. Competition: how crowded is this space
5. Recommended action: pursue now / later / skip

KATY'S SELLABLE SERVICES based on her skills:
- AI application development for small businesses
- Sales training tool setup (CCPractice-style)
- Contractor intake automation (Smart Intake-style)
- Multi-agent pipeline setup for content creation
- AI implementation consulting

Always prioritize opportunities that can generate income quickly.
Katy needs near-term revenue - flag anything that takes 6+ months to pay off.
"""
        result = await self.call_claude(system, task)
        self.log_task_result(task, result[:200])
        return result
