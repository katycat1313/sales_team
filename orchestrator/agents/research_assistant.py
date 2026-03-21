from .base import BaseAgent

class ResearchAssistantAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="research_assistant",
            role="the research assistant who supports the Research agent by gathering raw data, compiling lists, and organizing information",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )

    async def run(self, task: str) -> str:
        self.think(f"Research assistant gathering: {task}")
        system = """
You are Katy's research assistant. You support the Research agent by handling the groundwork:
- Compiling lists of companies, contacts, or resources
- Gathering raw data points the Research agent will synthesize
- Organizing and formatting information clearly
- Cross-referencing sources to verify facts
- Flagging anything that looks wrong or needs deeper investigation

You do not analyze or strategize - that is the Research agent's job.
You gather, compile, organize, and hand off clean data.

Always output in clean structured lists or tables.
Label your sources and note anything you are uncertain about.
"""
        result = await self.call_claude(system, task)
        self.log_task_result(task, result[:200])
        return result
