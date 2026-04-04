"""
GBP Researcher Agent
--------------------
Takes prospects found by GBP Scout and builds a full intel dossier:
- Owner/decision maker name
- Business email/phone
- Website quality check
- Social media presence
- Best pitch angle based on their specific GBP gaps

Chains from GBP Scout output and feeds into Outreach Agent.
"""

import json
import re
from .base import BaseAgent
from memory.memory import get_prospects, update_prospect


class GBPResearcherAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="gbp_researcher",
            role="the business intelligence specialist who researches GBP prospects and builds pitch dossiers",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval,
        )

    async def _research_business(self, business_name: str, location: str, gbp_issues: list) -> dict:
        """Browse business website + Google to gather intel."""
        intel = {
            "business_name": business_name,
            "location": location,
            "website_content": "",
            "owner_name": "",
            "email": "",
            "phone": "",
            "social_presence": {},
        }

        # Try to browse the business website if we have it
        try:
            from tools.browser import browser_tool
            from tools.gbp_audit import audit_gbp

            # First get the website URL from a Google search
            search_results = await audit_gbp(business_name, location)
            website_url = search_results.get("found", {}).get("website", "")

            if website_url and "http" in website_url:
                self.think(f"Browsing website: {website_url}")
                if not browser_tool.browser:
                    await browser_tool.start()
                page_text = await browser_tool.general_browse(website_url)
                intel["website_content"] = page_text[:3000]
                intel["website_url"] = website_url

                # Extract email from page text
                email_match = re.search(
                    r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
                    page_text
                )
                if email_match:
                    found_email = email_match.group()
                    # Filter out generic/noreply addresses
                    if not any(x in found_email.lower() for x in ["noreply", "example", "yourname", "privacy"]):
                        intel["email"] = found_email

                # Extract phone from page text
                phone_match = re.search(
                    r'(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
                    page_text
                )
                if phone_match:
                    intel["phone"] = phone_match.group()

        except Exception as e:
            self.think(f"Website browse failed: {e}")

        return intel

    async def run(self, task: str) -> str:
        self.think(f"GBP Researcher starting: {task[:100]}")

        task_lower = task.lower()

        # Pull business names directly from scout handoff bullets when available.
        scoped_names = set()
        for line in task.splitlines():
            line = line.strip()
            if line.startswith("• ") and "|" in line:
                scoped_names.add(line[2:].split("|", 1)[0].strip())

        # Try to parse the original niche/location from chained task context.
        niche_match = re.search(r"find\s+(.+?)\s+in\s+([A-Za-z .]+,?\s*[A-Z]{2})", task, re.IGNORECASE)
        scoped_niche = ""
        scoped_location = ""
        if niche_match:
            scoped_niche = niche_match.group(1).strip().lower()
            scoped_location = niche_match.group(2).strip().lower()

        # If this task includes scout findings, only use scoped prospects.
        use_scoped_mode = "[gbp_scout findings]" in task_lower or "top prospects for research" in task_lower

        # Get unresearched prospects from database (stage = 'found')
        prospects = get_prospects(stage="found", limit=100)

        if use_scoped_mode:
            filtered = []
            for p in prospects:
                name = (p.get("business_name") or "").strip()
                niche = (p.get("niche") or "").strip().lower()
                location = (p.get("location") or "").strip().lower()

                if scoped_names and name in scoped_names:
                    filtered.append(p)
                    continue

                if scoped_niche and scoped_location and scoped_niche in niche and scoped_location in location:
                    filtered.append(p)

            prospects = filtered

        if not prospects:
            # Also check if task mentions specific businesses
            self.think("No 'found' stage prospects in DB — researching from task context")
            prospects = []

        dossiers = []

        if prospects:
            self.act(f"Researching {len(prospects)} prospects from database")
            for p in prospects[:5]:  # Research up to 5 at a time
                biz_name = p.get("business_name", "")
                loc = p.get("location", "")
                issues = json.loads(p.get("gbp_issues", "[]")) if isinstance(p.get("gbp_issues"), str) else p.get("gbp_issues", [])

                self.think(f"Researching: {biz_name}")
                intel = await self._research_business(biz_name, loc, issues)

                # Use Gemini to build the pitch dossier from gathered intel
                research_system = f"""
You are researching a small business for a GBP optimization sales pitch.

Business: {biz_name}
Location: {loc}
GBP Issues Found: {', '.join(issues) if issues else 'Multiple gaps identified'}
Website Content: {intel.get('website_content', 'Not available')[:1500]}

Build a concise sales intel dossier:
1. BUSINESS PROFILE: What they do, how long in business (estimate), customer type
2. DECISION MAKER: Most likely owner/manager name and how to address them
3. PAIN POINTS: Why their GBP gaps are costing them money RIGHT NOW (be specific)
4. PITCH ANGLE: The single most compelling reason for them to fix their GBP
5. BEST CONTACT METHOD: email / phone / walk-in (based on their business type)
6. ESTIMATED VALUE: What a fixed GBP is worth to their business (new customers/month)

Be specific and actionable. This goes directly to the outreach writer.
"""
                dossier_text = await self.call_llm(research_system, f"Research {biz_name} in {loc}")

                # Save research to database
                update_prospect(
                    business_name=biz_name,
                    location=loc,
                    research_notes=dossier_text[:2000],
                    email=intel.get("email", ""),
                    phone=intel.get("phone", p.get("phone", "")),
                    pipeline_stage="researched",
                )

                dossiers.append({
                    "business": biz_name,
                    "location": loc,
                    "email": intel.get("email", ""),
                    "dossier": dossier_text,
                })

        else:
            msg = (
                "GBP RESEARCHER SKIPPED — no scoped real prospects from current scout run. "
                "Pipeline halted to avoid hypothetical dossiers."
            )
            self.act("No scoped prospects available; skipping research")
            self.log_task_result(task, msg)
            return msg

        # Build handoff summary for Outreach Agent
        output_lines = [
            f"GBP RESEARCHER COMPLETE — {len(dossiers)} businesses researched",
            "",
        ]
        for d in dossiers:
            output_lines.append(f"=== {d['business']} ===")
            if d.get("email"):
                output_lines.append(f"Contact email: {d['email']}")
            output_lines.append(d.get("dossier", ""))
            output_lines.append("")

        output_lines.append(
            "NEXT: Hand these dossiers to the outreach agent to draft personalized emails."
        )

        result = "\n".join(output_lines)
        self.log_task_result(task, result[:300])
        self.act(f"Research complete: {len(dossiers)} dossiers built")
        return result

