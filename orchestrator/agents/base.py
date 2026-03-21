# coding: utf-8
import os
from typing import Callable
from memory.memory import (
    remember, recall, recall_all, add_note, get_notes,
    log_task, get_recent_tasks, get_memory_summary
)
from google import genai
from google.genai import types

DEFAULT_MODELS = [
    "gemini-2.5-flash",
    "gemini-1.5-flash",
]

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
        self.think(f"Thinking about: {user_message[:80]}...")

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            self.act("Gemini API key missing; cannot run model call")
            return "Gemini is not configured yet. Set GEMINI_API_KEY in your environment and restart the service."

        client = genai.Client(api_key=api_key)

        my_memory = self.recall_all()
        memory_context = ""
        if my_memory:
            memory_context = f"\n\nYour current memory:\n{my_memory}"

        full_system = f"""You are {self.name}, {self.role}

You are part of Katy's elite GBP sales crew. The mission is simple:
find local businesses with broken Google Business Profiles, reach out with a compelling pitch,
and close them as paying clients at $197/each ($99 deposit upfront, $98 on delivery).

This is Katy's primary income right now. Every action you take should move a prospect
closer to becoming a paying client. Be direct, persuasive, and specific.
Never be vague. Never waste time. Think like a closer.

Key facts:
- GBP optimization is a FAST, TANGIBLE service — results are visible immediately
- $197 is less than one missed customer for most small businesses
- The biggest objection is "I didn't know my profile was broken" — show them the proof
- Local service businesses (plumbers, roofers, salons, auto repair) are the best targets
- Facebook DM + email combo gets the best response rates
- Always flag anything that requires sending a message or spending money for Katy's approval

Here is everything you need to know about Katy:
---
{self.katy_brief}
---
{memory_context}

{system_prompt}"""

        requested_model = (os.getenv("GEMINI_MODEL") or "").strip()
        models_to_try = [requested_model] if requested_model else []
        for fallback in DEFAULT_MODELS:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        last_error = None
        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=user_message,
                    config=types.GenerateContentConfig(
                        system_instruction=full_system,
                        max_output_tokens=1500,
                        temperature=0.7,
                    )
                )
                self.act(f"Gemini response generated with model: {model_name}")
                return response.text
            except Exception as exc:
                last_error = exc
                self.think(f"Gemini call failed with model {model_name}: {exc}")
                continue

        return f"Gemini request failed across configured models. Last error: {last_error}"

    async def run(self, task: str) -> str:
        raise NotImplementedError