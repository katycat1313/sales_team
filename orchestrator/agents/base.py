import anthropic
import os
from typing import Callable
from memory.memory import (
    remember, recall, recall_all, add_note, get_notes,
    log_task, get_recent_tasks, get_memory_summary
)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

class BaseAgent:
    def __init__(self, name: str, role: str, katy_brief: str, log_event: Callable, request_approval: Callable):
        self.name = name
        self.role = role
        self.katy_brief = katy_brief
        self.log_event = log_event
        self.request_approval = request_approval

    def remember(self, key: str, value: str):
        remember(self.name, key, value)

    def recall(self, key: str):
        return recall(self.name, key)

    def recall_all(self):
        return recall_all(self.name)

    def note(self, content: str, category: str = "general"):
        add_note(self.name, content, category)

    def get_notes(self, category: str = None):
        return get_notes(self.name, category)

    def log_task_result(self, task: str, result: str):
        log_task(self.name, task, result)

    def think(self, thought: str):
        self.log_event(self.name, "thought", thought)

    def act(self, action: str):
        self.log_event(self.name, "action", action)

    def needs_approval(self, action: str, details: dict):
        self.think(f"This requires Katy's approval: {action}")
        return self.request_approval(self.name, action, details)

    async def call_claude(self, system_prompt: str, user_message: str) -> str:
        self.think(f"Calling Claude: {user_message[:80]}...")

        # Pull agent's own memory to include as context
        my_memory = self.recall_all()
        memory_context = ""
        if my_memory:
            memory_context = f"\n\nYour current memory:\n{my_memory}"

        full_system = f"""You are {self.name}, {self.role}

You work as part of Katy's personal AI agent team. Your job is to help her find work,
land interviews, and grow her career. Always act in her best interest.

Here is everything you need to know about Katy:
---
{self.katy_brief}
---
{memory_context}

Be direct, proactive, and specific. Never be vague. Think step by step.
Always flag anything that requires sending, posting, or spending money for Katy's approval.
{system_prompt}"""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": user_message}],
            system=full_system
        )

        return message.content[0].text

    async def run(self, task: str) -> str:
        raise NotImplementedError
