# coding: utf-8
import os
from typing import Callable, Optional
from memory.memory import (
    remember, recall, recall_all, add_note, get_notes,
    log_task, get_recent_tasks, get_memory_summary
)
from google import genai
from google.genai import types

# Try to import Vertex AI; gracefully fall back if not installed
try:
    import vertexai
    from vertexai.generative_models import GenerativeModel
    VERTEX_AI_AVAILABLE = True
except ImportError:
    VERTEX_AI_AVAILABLE = False

DEFAULT_MODELS = [
    "gemini-3.1-pro",  # Vertex AI model name (different from Gemini API)
    "gemini-2.5-flash",
]

_GEMINI_CLIENT = None
_GEMINI_CLIENT_KEY = None
_VERTEX_CLIENT = None
_VERTEX_PROJECT = None
_VERTEX_LOCATION = None

GBP_AGENTS = {
    "coordinator",
    "gbp_scout",
    "gbp_researcher",
    "gbp_sales",
    "outreach",
    "sales",
    "sales_ops",
    "small_biz_expert",
    "lead_gen",
    "biz_dev",
    "marketing",
}


def _get_gemini_client(api_key: str):
    """Cached Gemini API client (Google AI Studio / free tier)"""
    global _GEMINI_CLIENT, _GEMINI_CLIENT_KEY
    if _GEMINI_CLIENT and _GEMINI_CLIENT_KEY == api_key:
        return _GEMINI_CLIENT
    _GEMINI_CLIENT = genai.Client(api_key=api_key)
    _GEMINI_CLIENT_KEY = api_key
    return _GEMINI_CLIENT


def _get_vertex_client(project_id: str, location: str = "us-central1"):
    """Cached Vertex AI client using Application Default Credentials (ADC)"""
    global _VERTEX_CLIENT, _VERTEX_PROJECT, _VERTEX_LOCATION
    if _VERTEX_CLIENT and _VERTEX_PROJECT == project_id and _VERTEX_LOCATION == location:
        return _VERTEX_CLIENT
    if not VERTEX_AI_AVAILABLE:
        return None
    try:
        vertexai.init(project=project_id, location=location)
        model_name = (os.getenv("VERTEX_MODEL") or "gemini-2.5-flash").strip()
        _VERTEX_CLIENT = GenerativeModel(model_name)
        _VERTEX_PROJECT = project_id
        _VERTEX_LOCATION = location
        return _VERTEX_CLIENT
    except Exception as e:
        print(f"Vertex AI init failed: {e}")
        return None


def _use_vertex_ai() -> bool:
    """Check if Vertex AI is configured and should be used"""
    return VERTEX_AI_AVAILABLE and os.getenv("VERTEX_AI_PROJECT_ID") is not None


def _truncate_text(value: str, limit: int) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[truncated]"

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

    async def call_llm(self, system_prompt: str, user_message: str) -> str:
        """
        Call LLM through Vertex AI, with optional Gemini API fallback.
        """
        self.think(f"Thinking about: {user_message[:80]}...")

        prefer_vertex = _use_vertex_ai()
        if prefer_vertex:
            vertex_result = await self._call_vertex_ai(system_prompt, user_message)
            lower_result = (vertex_result or "").lower()
            has_vertex_failure = (
                lower_result.startswith("vertex ai error")
                or "resource exhausted" in lower_result
                or "429" in lower_result
                or "initialization failed" in lower_result
                or "not configured" in lower_result
            )

            if not has_vertex_failure:
                return vertex_result

            self.think("Vertex AI failed; attempting Gemini API fallback")

        return await self._call_gemini_api(system_prompt, user_message)

    async def _call_vertex_ai(self, system_prompt: str, user_message: str) -> str:
        """Call Vertex AI with ADC authentication"""
        try:
            project_id = os.getenv("VERTEX_AI_PROJECT_ID")
            location = os.getenv("VERTEX_AI_LOCATION", "us-central1")

            if not project_id:
                return "Vertex AI project ID not configured (VERTEX_AI_PROJECT_ID)"

            client = _get_vertex_client(project_id, location)
            if not client:
                self.act("Vertex AI client init failed; Gemini API fallback is disabled")
                return "Vertex AI client initialization failed. Check project/location and ADC credentials."

            my_memory = self.recall_all()
            memory_context = ""
            if my_memory:
                memory_context = f"\n\nYour current memory:\n{my_memory}"

            katy_brief_compact = _truncate_text(self.katy_brief, 2200)
            memory_compact = _truncate_text(memory_context, 1200)

            if self.name in GBP_AGENTS:
                mission_context = """
You are part of Katy's GBP sales crew. Focus on finding local businesses with broken Google Business Profiles,
crafting proof-based outreach, and moving prospects toward paid GBP optimization services.
Always flag any message-sending or spend actions for Katy approval.
"""
            else:
                mission_context = """
You are part of Katy's specialist AI team. Focus on the requested task and provide concrete, actionable output.
Use Katy's real background and projects, avoid generic filler, and keep responses practical.
"""

            full_system = f"""You are {self.name}, {self.role}

{mission_context}

Here is everything you need to know about Katy:
---
{katy_brief_compact}
---
{memory_compact}

{system_prompt}"""

            try:
                response = client.generate_content(
                    [full_system, user_message],
                    generation_config={"max_output_tokens": 1500, "temperature": 0.7}
                )
                self.act(f"Vertex AI response generated from {project_id}/{location}")
                try:
                    text = response.text
                    if text:
                        return text
                except Exception:
                    pass

                # Fallback: extract text parts manually if the SDK helper fails.
                candidates = getattr(response, "candidates", None) or []
                extracted_parts = []
                for cand in candidates:
                    content = getattr(cand, "content", None)
                    parts = getattr(content, "parts", None) or []
                    for part in parts:
                        part_text = getattr(part, "text", None)
                        if part_text:
                            extracted_parts.append(part_text)

                if extracted_parts:
                    return "\n".join(extracted_parts)

                # Retry once with a leaner prompt if the model returned no text.
                retry_system = f"You are {self.name}. Be concise and direct.\n\n{_truncate_text(system_prompt, 700)}"
                retry_response = client.generate_content(
                    [retry_system, _truncate_text(user_message, 1200)],
                    generation_config={"max_output_tokens": 700, "temperature": 0.5}
                )
                try:
                    retry_text = retry_response.text
                    if retry_text:
                        return retry_text
                except Exception:
                    pass

                return "Vertex AI returned an empty response. Please retry the task."
            except Exception as exc:
                self.think(f"Vertex AI call failed: {exc}")
                return f"Vertex AI error: {exc}"

        except Exception as e:
            self.act(f"Vertex AI initialization error: {e}")
            return f"Vertex AI initialization error: {e}"

    async def _call_gemini_api(self, system_prompt: str, user_message: str) -> str:
        """Call Gemini API directly using API key (Google AI Studio)."""
        try:
            api_key = (
                os.getenv("GEMINI_API_KEY")
                or os.getenv("GOOGLE_API_KEY")
                or ""
            ).strip()
            if not api_key:
                return (
                    "Vertex AI failed and no Gemini API key is configured. "
                    "Set GEMINI_API_KEY (or GOOGLE_API_KEY) to enable fallback."
                )

            client = _get_gemini_client(api_key)
            my_memory = self.recall_all()
            memory_context = ""
            if my_memory:
                memory_context = f"\n\nYour current memory:\n{my_memory}"

            katy_brief_compact = _truncate_text(self.katy_brief, 2200)
            memory_compact = _truncate_text(memory_context, 1200)

            if self.name in GBP_AGENTS:
                mission_context = """
You are part of Katy's GBP sales crew. Focus on finding local businesses with broken Google Business Profiles,
crafting proof-based outreach, and moving prospects toward paid GBP optimization services.
Always flag any message-sending or spend actions for Katy approval.
"""
            else:
                mission_context = """
You are part of Katy's specialist AI team. Focus on the requested task and provide concrete, actionable output.
Use Katy's real background and projects, avoid generic filler, and keep responses practical.
"""

            full_system = f"""You are {self.name}, {self.role}

{mission_context}

Here is everything you need to know about Katy:
---
{katy_brief_compact}
---
{memory_compact}

{system_prompt}"""

            model_name = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
            response = client.models.generate_content(
                model=model_name,
                contents=[full_system, user_message],
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=1500,
                ),
            )

            text = getattr(response, "text", "") or ""
            if text.strip():
                self.act(f"Gemini API response generated with {model_name}")
                return text

            return "Gemini API returned an empty response. Please retry the task."
        except Exception as e:
            self.act(f"Gemini API error: {e}")
            return f"Gemini API error: {e}"

    async def call_claude(self, system_prompt: str, user_message: str) -> str:
        # Backward-compatible alias for older code paths.
        return await self.call_llm(system_prompt, user_message)

    async def run(self, task: str) -> str:
        raise NotImplementedError
