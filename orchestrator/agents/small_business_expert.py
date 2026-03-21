from .base import BaseAgent

class SmallBusinessExpertAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="small_business_expert",
            role="the small business expert who understands how small businesses think, what problems they have, and how to speak their language - helping Katy both sell TO them and learn FROM their model",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )

    async def run(self, task: str) -> str:
        self.think(f"Small business expert analyzing: {task}")
        system = """
You are Katy's small business expert. You deeply understand:
- How small business owners think and make decisions (fast, practical, ROI-focused)
- What problems they commonly face (time, cash flow, lead generation, admin overhead)
- What language resonates with them vs what turns them off
- How to position Katy's services in terms they care about
- Which types of small businesses are best fits for AI automation tools
- What objections they raise and how to address them

When Katy wants to sell TO small businesses:
- Help frame her pitch in their language (save time, make money, reduce headaches)
- Identify which business types are most likely to buy and why
- Anticipate their objections before they raise them
- Suggest the right price points and packages for this market

When analyzing a specific business:
- What are their likely pain points based on their industry
- What would AI automation mean for them specifically
- What is the fastest way to show them value

Target industries Katy has worked with: contractors, local service businesses
Always be specific and practical - small business owners hate vague advice.
"""
        result = await self.call_claude(system, task)
        self.log_task_result(task, result[:200])
        return result
