"""
GBP Scout Agent
---------------
Finds local businesses with missing, incomplete, or outdated
Google Business Profiles. These are Katy's sales prospects.

Inputs:  "find plumbers in Austin TX"
         "scan restaurants in downtown Chicago"
Outputs: List of prospects with GBP scores saved to database
"""

import json
from .base import BaseAgent
from memory.memory import save_prospect, get_prospects


class GBPScoutAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="gbp_scout",
            role="the GBP prospect hunter who finds local businesses with missing or broken Google Business Profiles",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval,
        )

    # Best niches for GBP sales — high ticket, owner-operated, search-driven
    PRIME_NICHES = [
        "plumbers", "HVAC contractors", "electricians",
        "auto repair shops", "roofers", "general contractors",
        "dentists", "chiropractors", "hair salons", "barber shops"
    ]

    # High-population cities across the US for maximum reach
    TARGET_CITIES = [
        "Houston TX", "Phoenix AZ", "San Antonio TX", "Dallas TX",
        "Jacksonville FL", "Austin TX", "Columbus OH", "Charlotte NC",
        "Indianapolis IN", "Fort Worth TX", "Memphis TN", "Louisville KY",
        "Baltimore MD", "Milwaukee WI", "Albuquerque NM", "Tucson AZ",
        "Fresno CA", "Sacramento CA", "Mesa AZ", "Kansas City MO"
    ]

    async def run(self, task: str) -> str:
        self.think(f"GBP Scout scanning: {task}")

        import re

        # Check if this is an autonomous sweep or a specific request
        is_auto_sweep = any(word in task.lower() for word in [
            "sweep", "scan everywhere", "find clients", "bring clients",
            "auto", "anywhere", "best targets", "honeypot"
        ])

        if is_auto_sweep:
            # Pick the best niche + city combo automatically
            import random
            niche = random.choice(self.PRIME_NICHES[:5])   # Top 5 niches
            location = random.choice(self.TARGET_CITIES[:10])  # Top 10 cities
            limit = 20
            self.act(f"Auto-selecting best target: {niche} in {location}")
        else:
            # Parse specific request
            parse_system = """
Extract the business niche and location from the task.
Return ONLY valid JSON: {"niche": "...", "location": "...", "limit": 15}
If no location given, pick the best US city for that niche.
If no niche given, pick plumbers — highest GBP conversion rate.
"""
            parsed_json = await self.call_claude(parse_system, task)

            try:
                match = re.search(r'\{[^}]+\}', parsed_json, re.DOTALL)
                params = json.loads(match.group()) if match else {}
            except Exception:
                params = {}

            niche    = params.get("niche", "plumbers")
            location = params.get("location", "Houston TX")
            limit    = min(int(params.get("limit", 15)), 25)

        self.act(f"Scanning Google Maps: {niche} in {location} (up to {limit} businesses)")

        # Run the actual GBP audit
        try:
            from tools.gbp_audit import run_prospect_scan
            prospects = await run_prospect_scan(niche, location, limit=limit)
        except Exception as e:
            self.think(f"Browser scan failed: {e} — generating research-based prospects instead")
            prospects = []

        if not prospects or (len(prospects) == 1 and "error" in prospects[0]):
            error_msg = prospects[0].get("error", "scan failed") if prospects else "no results"
            self.think(f"Browser scan unavailable: {error_msg}")
            # Fall back: ask Gemini to identify likely prospect types in that niche
            fallback_system = f"""
The automated GBP scan is unavailable right now.
Based on your knowledge, list 10 specific types of {niche} businesses in {location}
that are most likely to have incomplete Google Business Profiles.
For each, explain the GBP gaps they typically have.
Format as JSON array: [{{"business_type": "...", "typical_issues": ["...", "..."], "priority": "HOT/WARM"}}]
"""
            return await self.call_claude(fallback_system, task)

        # Save prospects to database
        saved_count = 0
        for p in prospects:
            if "error" in p:
                continue
            # Phone: prefer Maps/audit found dict, fall back to top-level (YP/Yelp)
            phone = (p.get("found") or {}).get("phone") or p.get("phone", "")
            website = (p.get("found") or {}).get("website") or p.get("website", "")
            is_new = save_prospect(
                business_name=p.get("name", ""),
                location=location,
                niche=niche,
                phone=phone,
                website=website,
                maps_url=p.get("maps_url", ""),
                gbp_score=p.get("score", 0),
                gbp_issues=p.get("issues", []),
                priority=p.get("priority", "WARM"),
                audit_data=p,
                pipeline_stage="found",
            )
            if is_new:
                saved_count += 1

        # Build summary for handoff to GBP Researcher
        hot_prospects = [p for p in prospects if p.get("priority") == "HOT"]
        warm_prospects = [p for p in prospects if p.get("priority") == "WARM"]

        summary_lines = [
            f"GBP SCOUT RESULTS — {niche} in {location}",
            f"Scanned: {len(prospects)} businesses | New prospects saved: {saved_count}",
            f"HOT (missing GBP or unclaimed): {len(hot_prospects)}",
            f"WARM (incomplete GBP): {len(warm_prospects)}",
            "",
            "TOP PROSPECTS FOR RESEARCH:",
        ]

        for p in prospects[:8]:
            issues_preview = "; ".join(p.get("issues", [])[:3])
            summary_lines.append(
                f"• {p.get('name', 'Unknown')} | Score: {p.get('score', '?')}/10 | "
                f"Priority: {p.get('priority', '?')} | Issues: {issues_preview}"
            )

        summary_lines.append(
            "\nHand off to gbp_researcher with business names and location for deep research."
        )

        result = "\n".join(summary_lines)
        self.log_task_result(task, result[:300])
        self.act(f"Scout complete: {len(prospects)} prospects found, {saved_count} new")
        return result
