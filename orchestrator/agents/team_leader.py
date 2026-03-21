# coding: utf-8
from .base import BaseAgent
from memory.memory import get_memory_summary, get_recent_tasks, add_note

class TeamLeaderAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="team_leader",
            role="the team leader who coordinates all agents and gets real work done for Katy",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )
        self.conversation_history = []

    async def handle_message(self, message: str) -> str:
        self.think(f"Katy says: {message}")

        self.conversation_history.append(f"Katy: {message}")

        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]

        history_str = "\n".join(self.conversation_history[-10:])

        mem = get_memory_summary()
        recent = get_recent_tasks(limit=5)
        recent_str = "\n".join([f"- {t['agent']}: {t['task'][:60]}" for t in recent]) or "None yet"

        system = f"""
You are the team leader of Katy's AI agent team.

CONVERSATION SO FAR:
{history_str}

MEMORY SNAPSHOT:
- Jobs found: {mem.get('jobs_total', 0)}
- Contacts found: {mem.get('contacts_total', 0)}
- Tasks today: {mem.get('tasks_today', 0)}

RECENT AGENT ACTIVITY:
{recent_str}

YOUR RULES:
1. Read the conversation history carefully - never forget what was said
2. When Katy says bring clients or find work - give her REAL specific results, not a plan
3. When Katy says find jobs - give her REAL specific job listings
4. Never just describe what you will do - DO it and report back
5. Be direct and short - she is busy
6. If she says ok, yes, go ahead - she is approving whatever you just proposed, execute it
"""
        response = await self.call_claude(system, message)
        self.conversation_history.append(f"Team Leader: {response}")
        self.log_task_result(message, response[:200])
        return response

    async def run(self, task: str) -> str:
        return await self.handle_message(task)