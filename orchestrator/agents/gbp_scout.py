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
import re
import random
from .base import BaseAgent
from memory.memory import save_prospect, get_prospects
from constants import TARGET_CITIES, ALLOWED_TARGET_NICHES, DEFAULT_TARGET_NICHE


class GBPScoutAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="gbp_scout",
            role="the GBP prospect hunter who finds local businesses with missing or broken Google Business Profiles",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval,
        )

    async def run(self, task: str) -> str:
        self.think(f"GBP Scout scanning: {task}")

        allowed_niches = {n.lower() for n in ALLOWED_TARGET_NICHES}

        # Check if this is an autonomous sweep or a specific request
        is_auto_sweep = any(word in task.lower() for word in [
            "sweep", "scan everywhere", "find clients", "bring clients",
            "auto", "anywhere", "best targets", "honeypot"
        ])

        if is_auto_sweep:
            # Pick the best niche + city combo automatically
            niche = random.choice(ALLOWED_TARGET_NICHES)
            location = random.choice(TARGET_CITIES[:10])  # Top 10 cities
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
            parsed_json = await self.call_llm(parse_system, task)

            try:
                match = re.search(r'\{[^}]+\}', parsed_json, re.DOTALL)
                params = json.loads(match.group()) if match else {}
            except Exception:
                params = {}

            niche    = params.get("niche", DEFAULT_TARGET_NICHE)
            location = params.get("location", "Houston TX")
            limit    = min(int(params.get("limit", 15)), 25)

        # Hard gate: only run approved niches.
        if (niche or "").strip().lower() not in allowed_niches:
            original_niche = niche
            niche = DEFAULT_TARGET_NICHE
            self.act(
                f"Requested niche '{original_niche}' is outside allowed targets; using {DEFAULT_TARGET_NICHE}"
            )

        self.act(f"Scanning Google Maps: {niche} in {location} (up to {limit} businesses)")

        # Run the actual GBP audit
        try:
            from tools.gbp_audit import run_prospect_scan
            prospects = await run_prospect_scan(niche, location, limit=limit)
        except Exception as e:
            self.think(f"Browser scan failed: {e} — generating research-based prospects instead")
            prospects = []

        # Supplement: mine reviews for call complaints and elevate priority
        try:
            from tools.review_miner import scan_for_call_complaints
            complaint_prospects = await scan_for_call_complaints(niche, location, limit=8)
            # Merge complaint data into existing prospects or add new ones
            existing_names = {p.get("name", "").lower() for p in prospects}
            for cp in complaint_prospects:
                cp_name = cp.get("name", "").lower()
                if cp_name in existing_names:
                    # Elevate existing prospect priority if they have complaint signals
                    for p in prospects:
                        if p.get("name", "").lower() == cp_name:
                            p["priority"] = "HOT"
                            p["complaint_score"] = cp.get("complaint_score", 0)
                            p["complaint_keywords"] = cp.get("complaint_keywords", [])
                            p["complaint_reviews"] = cp.get("complaint_reviews", [])
                            if cp.get("complaint_reviews"):
                                p.setdefault("issues", []).insert(
                                    0, f"Review complaint: \"{cp['complaint_reviews'][0][:120]}\""
                                )
                            break
                elif cp.get("complaint_score", 0) > 0:
                    # Add as new prospect with complaint data
                    cp["source"] = "review_miner"
                    prospects.append(cp)
        except Exception as e:
            self.think(f"Review mining supplemental scan failed (non-blocking): {e}")

        if not prospects or (len(prospects) == 1 and "error" in prospects[0]):
            error_msg = prospects[0].get("error", "scan failed") if prospects else "no results"
            self.think(f"Browser scan unavailable: {error_msg}")
            return (
                "GBP SCOUT FAILED — no real prospects were collected. "
                f"Reason: {error_msg}. "
                "Pipeline halted to avoid hypothetical data."
            )

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

