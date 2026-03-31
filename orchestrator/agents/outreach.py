import json
import os
import re
from .base import BaseAgent
from memory.memory import save_contact, get_contacts, contact_exists, mark_contacted, get_prospects, update_prospect

class OutreachAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        # Load persuasion knowledge base
        persuasion_kb = ""
        try:
            kb_path = os.path.join(os.path.dirname(__file__), "../memory/persuasion_techniques.md")
            with open(kb_path, "r") as f:
                persuasion_kb = f.read()
        except Exception as e:
            print(f"[Outreach] Could not load persuasion KB: {e}")

        super().__init__(
            name="outreach",
            role=(
                "the outreach specialist who crafts highly persuasive, personalized messages for AI answering-service "
                "sales in Katy's authentic voice. You write like a real person — conversational, specific, "
                "never salesy. Every message leads with their specific problem, uses their name, references "
                "exactly what you found about their call-handling pain, and makes one clear low-pressure ask. "
                "You never use generic templates — every message is unique to that business.\n\n"
                "MESSAGE RULES:\n"
                "- Use 'you/your' not 'we/our'\n"
                "- Max 3 problems per message\n"
                "- Always include 'because' to explain why it matters\n"
                "- End with a soft CTA that gives them autonomy\n"
                "- Keep DMs under 150 words. Emails under 200 words.\n\n"
                f"PERSUASION KNOWLEDGE BASE:\n{persuasion_kb}"
            ),
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )

    def _extract_email_parts(self, draft: str) -> dict:
        """Extract TO, SUBJECT, BODY from structured draft."""
        parts = {"to": "", "subject": "", "body": ""}
        to_match = re.search(r'TO:\s*(.+)', draft)
        subject_match = re.search(r'SUBJECT:\s*(.+)', draft)
        body_match = re.search(r'BODY:\s*([\s\S]+?)(?:---|\Z)', draft)
        if to_match:
            parts["to"] = to_match.group(1).strip()
        if subject_match:
            parts["subject"] = subject_match.group(1).strip()
        if body_match:
            parts["body"] = body_match.group(1).strip()
        return parts

    async def run(self, task: str) -> str:
        self.think(f"Outreach drafting: {task[:100]}")

        # Check if this is pipeline outreach for answering-service sales
        is_pipeline = any(x in task.lower() for x in ["lead", "prospect", "dossier", "research", "missed call", "answering", "gbp researcher", "gbp"])

        # Pull researched prospects from DB for pipeline outreach
        prospects_with_email = []
        if is_pipeline:
            researched = get_prospects(stage="researched", limit=5)
            prospects_with_email = [p for p in researched if p.get("email")]

        if is_pipeline and prospects_with_email:
            # Draft one personalized email per prospect
            all_drafts = []
            for prospect in prospects_with_email:
                biz_name = prospect.get("business_name", "")
                location = prospect.get("location", "")
                email = prospect.get("email", "")
                issues = prospect.get("gbp_issues", "[]")
                if isinstance(issues, str):
                    try:
                        issues = json.loads(issues)
                    except Exception:
                        issues = []
                research_notes = prospect.get("research_notes", "")

                system = f"""
You are writing a cold outreach email FROM Katy (ifixprofiles@gmail.com) TO a local business owner.
Katy's service: AI answering-service setup for service businesses that lose revenue from missed calls.
Offer tiers:
- Starter: $500 setup + $97/month
- Standard: $1,000 setup + $197/month
- Pro: $2,000 setup + $297/month

Business: {biz_name} in {location}
Known pain signals: {', '.join(issues) if issues else 'missed calls / delayed response risk'}
Research notes: {research_notes[:800] if research_notes else 'small local business'}

Write a SHORT, friendly cold email. Rules:
- Max 5 sentences in the body
- Lead with ONE specific missed-call or response-time problem you found
- Explain what it's costing them (missed calls, lost customers)
- Offer the simplest fitting tier first (Starter if unsure)
- End with a simple yes/no question

Output EXACTLY in this format (no extra text):
TO: {email}
SUBJECT: [subject line here]
BODY:
[email body here]
---
"""
                draft = await self.call_llm(system, f"Draft answering-service outreach for {biz_name}")
                parts = self._extract_email_parts(draft)

                if parts["subject"] and parts["body"]:
                    # Find social media profiles
                    facebook_url = ""
                    instagram_handle = ""
                    try:
                        from tools.browser import browser_tool
                        if not browser_tool.browser:
                            await browser_tool.start()
                        facebook_url = await browser_tool.find_facebook_page(biz_name, location)
                        instagram_handle = await browser_tool.find_instagram_handle(biz_name, location)
                    except Exception as e:
                        print(f"[Outreach] Social media lookup failed for {biz_name}: {e}")

                    self.needs_approval(
                        action="send_email",
                        details={
                            "to": email,
                            "subject": parts["subject"],
                            "body": parts["body"],
                            "prospect_name": biz_name,
                            "location": location,
                            "facebook_url": facebook_url,
                            "instagram_handle": instagram_handle,
                            "preview": f"To: {email}\nSubject: {parts['subject']}\n\n{parts['body'][:200]}..."
                        }
                    )
                    channels = []
                    if email: channels.append(f"email → {email}")
                    if facebook_url: channels.append("Facebook DM")
                    if instagram_handle: channels.append(f"Instagram @{instagram_handle}")
                    all_drafts.append(f"✅ {biz_name} — {' + '.join(channels) if channels else 'no contact found'}\nSubject: {parts['subject']}")
                    update_prospect(business_name=biz_name, location=location, pipeline_stage="draft_ready")

            result = "\n\n".join(all_drafts) if all_drafts else "No prospects with email addresses found. Researcher needs to find contact info first."
            self.act(f"Queued {len(all_drafts)} email drafts for approval")
            return result

        else:
            # General outreach (no researched prospects yet)
            contacted = get_contacts(status="contacted")
            already_contacted = "\n".join([f"- {c['name']}" for c in contacted]) if contacted else "None yet"

            system = f"""
You are Katy's outreach specialist. Write in her voice - direct, warm, real. Never corporate.

People already contacted: {already_contacted}

Draft a cold outreach message. Keep it to 4-5 sentences max.
Lead with something specific. End with a clear low-pressure ask.

Output EXACTLY in this format:
TO: [email if known, else 'unknown']
SUBJECT: [subject line]
BODY:
[message body]
---
"""
            draft = await self.call_llm(system, task)
            parts = self._extract_email_parts(draft)

            self.needs_approval(
                action="send_email",
                details={
                    "to": parts.get("to", ""),
                    "subject": parts.get("subject", ""),
                    "body": parts.get("body", ""),
                    "prospect_name": "unknown",
                    "location": "",
                    "preview": draft[:400]
                }
            )

            self.log_task_result(task, draft[:200])
            self.act("Outreach draft queued for approval")
            return draft

    async def send_approved_outreach(self, prospect_name: str, location: str, email: str, subject: str, body: str) -> dict:
        """
        Called AFTER Katy approves. Actually sends the email via Gmail.
        Updates the prospect's pipeline stage to 'outreach_sent'.
        """
        from tools.gmail_tool import send_email, is_configured

        if not is_configured():
            self.think("Gmail not configured — cannot send yet. Add GMAIL_ADDRESS and GMAIL_APP_PASSWORD to .env")
            return {"sent": False, "error": "Gmail not configured"}

        self.think(f"Sending approved outreach to {prospect_name} at {email}")
        result = send_email(to=email, subject=subject, body=body)

        if result.get("sent"):
            self.act(f"Email sent to {prospect_name} at {email}")
            mark_contacted(prospect_name, prospect_name)  # contacts table
            update_prospect(
                business_name=prospect_name,
                location=location,
                pipeline_stage="outreach_sent",
                outreach_sent_at=result.get("sent_at", ""),
            )
        else:
            self.think(f"Send failed: {result.get('error')}")

        return result

