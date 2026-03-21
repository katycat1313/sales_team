from .base import BaseAgent

class ResearchAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="research",
            role="the deep research specialist who investigates companies, markets, people, and opportunities thoroughly before anyone acts",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )

    async def run(self, task: str) -> str:
        self.think(f"Research agent investigating: {task}")
        system = """
You are Katy's deep research specialist. Before anyone pitches, applies, or reaches out - you do the homework.

Your research covers:
- Companies: culture, funding, tech stack, recent news, pain points, hiring signals
- People: background, role, what they care about, how to approach them
- Markets: who the buyers are, what problems exist, what solutions already exist
- Opportunities: is this worth pursuing, what is the risk, what is the upside

Output format - always use these four sections:
KEY FINDINGS (bullet points, most important first)
OPPORTUNITY ASSESSMENT (is this worth pursuing and why)
RECOMMENDED NEXT STEPS (which agent should act on this)
GAPS (what you could not find that someone should follow up on)

Be thorough but not bloated. Every sentence should earn its place.
"""
        result = await self.call_claude(system, task)
        self.note(f"Researched: {task[:80]}", "research_history")
        self.log_task_result(task, result[:200])
        self.act(f"Research complete: {task[:50]}")
        return result


class ResearchAssistantAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="research_assistant",
            role="the research assistant who supports the research agent with quick lookups and data collection",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )

    async def run(self, task: str) -> str:
        self.think(f"Research assistant handling: {task}")
        return "(stub)"

