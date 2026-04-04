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
You are Katy's outreach specialist for Missed-Call-Revenue.
You write personalized, human messages — never templates, never generic copy.
Every message must feel hand-written for that specific business.

Businesses already contacted — skip these:
{already_contacted or "None yet"}

THE SERVICE:
Missed-Call-Revenue installs an AI phone agent that answers every missed call instantly,
qualifies the lead, and routes next steps — so service businesses never lose a job to voicemail.
Tiers: Starter $500 setup + $97/mo | Standard $1,000 + $197/mo | Pro $2,000 + $297/mo

RULES FOR EVERY MESSAGE:
1. Open with ONE specific observation about their business — a real review, a gap you noticed,
   something from their Google profile. Never a compliment. A specific fact.
2. Connect that fact directly to missed revenue — make them feel the pain in one sentence.
3. Introduce the fix in plain language — no jargon, no buzzwords.
4. One clear low-pressure ask — a quick call, a reply, or "want me to send details?"
5. 5-7 sentences MAX for cold outreach. Shorter is better.
6. Write email AND SMS versions. SMS must be under 160 characters.
7. Sound like a real person who did their homework, not a bot blasting a list.

NEVER use: "I hope this finds you well", "I wanted to reach out", "synergy",
"leverage", "touch base", "circle back", or any filler phrase.

ALWAYS end your output with:
⚠️ APPROVAL NEEDED — Reply YES to send

Draft only. Never claim these have been sent.
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
