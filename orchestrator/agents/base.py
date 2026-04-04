import anthropic
import os
from typing import Callable
from memory.memory import (
    remember, recall, recall_all, add_note, get_notes,
    log_task, get_recent_tasks, get_memory_summary
)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Running totals — reset on restart, but logged to events each call
_total_input_tokens  = 0
_total_output_tokens = 0


def get_token_usage() -> dict:
    return {
        "input_tokens":  _total_input_tokens,
        "output_tokens": _total_output_tokens,
        "total_tokens":  _total_input_tokens + _total_output_tokens,
        # Rough cost estimate: Sonnet ~$3/M input, $15/M output
        "estimated_cost_usd": round(
            (_total_input_tokens / 1_000_000 * 3.0) +
            (_total_output_tokens / 1_000_000 * 15.0),
            4
        ),
    }


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

    async def call_claude(self, system_prompt: str, user_message: str, max_tokens: int = 1024) -> str:
        global _total_input_tokens, _total_output_tokens

        self.think(f"Calling Claude: {user_message[:80]}...")

        my_memory = self.recall_all()
        memory_context = f"\n\nYour memory:\n{my_memory}" if my_memory else ""

        full_system = (
            f"You are {self.name}, {self.role}\n\n"
            f"You are part of Katy's AI sales team for Missed-Call-Revenue — an AI answering service "
            f"for local service businesses. Your job is to help land clients and grow the business.\n\n"
            f"About Katy and the business:\n---\n{self.katy_brief}\n---"
            f"{memory_context}\n\n"
            f"Be direct and specific. Never vague. "
            f"Flag anything that involves sending a message or spending money for Katy's approval.\n"
            f"{system_prompt}"
        )

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": user_message}],
            system=full_system,
        )

        # Track usage
        usage = message.usage
        _total_input_tokens  += usage.input_tokens
        _total_output_tokens += usage.output_tokens
        self.log_event(
            self.name, "usage",
            f"tokens in={usage.input_tokens} out={usage.output_tokens} | "
            f"session total={_total_input_tokens + _total_output_tokens}"
        )

        return message.content[0].text

    # Alias used by some agents (gbp_researcher etc.)
    async def call_llm(self, system_prompt: str, user_message: str, max_tokens: int = 1024) -> str:
        return await self.call_claude(system_prompt, user_message, max_tokens)

    async def run(self, task: str) -> str:
        raise NotImplementedError
