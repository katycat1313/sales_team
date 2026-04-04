from .base import BaseAgent
from memory.memory import save_contact, get_contacts, contact_exists, mark_contacted

class OutreachAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="outreach",
            role="the outreach specialist who drafts personalized emails, LinkedIn messages, and follow-ups in Katy's voice",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )

    async def run(self, task: str) -> str:
        self.think(f"Outreach drafting: {task}")

        # Who have we already contacted?
        contacted = get_contacts(status="contacted")
        already_contacted = ""
        if contacted:
            already_contacted = "\n".join([f"- {c['name']} at {c['company']}" for c in contacted])

        system = f"""
You are Katy's outreach specialist. You write in her voice — direct, warm, real.
Never corporate. Never stiff. Always human.

People already contacted — DO NOT draft messages to these people again:
{already_contacted or "None yet"}

When drafting outreach:
1. Lead with something specific about the company or person
2. Connect Katy's actual projects to what they need
3. Keep it short — 4-6 sentences max for cold outreach
4. End with a clear, low-pressure ask
5. Sound like Katy — career changer at 40 who builds real AI apps

Katy's strongest talking points:
- Built CCPractice — real-time AI voice coaching (Deepgram + Claude + React)
- Built RawBlockAI — multi-agent B-roll video pipeline (Runway API + Docker)
- 10 years digital marketing + now building AI-integrated apps
- She ships things — not just tutorials

ALWAYS end your draft with:
⚠️ APPROVAL NEEDED — Reply YES to send this message

Never claim to send anything. Draft only.
"""
        result = await self.call_claude(system, task)

        self.remember("last_outreach", task)
        self.note(f"Draft created: {task[:80]}", "drafts")
        self.log_task_result(task, result[:200])
        self.act(f"Outreach draft ready — flagging for approval")

        self.needs_approval(
            action="send_outreach_message",
            details={"task": task, "draft_preview": result[:300]}
        )

        return result
