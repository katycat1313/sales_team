"""
Legacy Sales Agent (gbp_sales)
------------------------------
Backward-compatible sales closer that now sells Katy's AI answering-service offers.

Current offer ladder:
- Starter: $500 setup + $97/month
- Standard: $1,000 setup + $197/month
- Pro: $2,000 setup + $297/month
"""

import json
import os
from .base import BaseAgent
from memory.memory import get_prospects, update_prospect


STARTER_SETUP = 500.00
STANDARD_SETUP = 1000.00
PRO_SETUP = 2000.00

# Legacy aliases kept for callers that still reference old names.
OPTIMIZATION_PRICE = STANDARD_SETUP
SPLIT_DEPOSIT = STARTER_SETUP
SPLIT_FINAL = STANDARD_SETUP
RETAINER_PRICE = 197.00

# Legacy aliases kept for any callers that reference the old names
DEPOSIT_AMOUNT = SPLIT_DEPOSIT
FINAL_AMOUNT = SPLIT_FINAL


class GBPSalesAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        # Load persuasion knowledge base
        persuasion_kb = ""
        try:
            kb_path = os.path.join(os.path.dirname(__file__), "../memory/persuasion_techniques.md")
            with open(kb_path, "r") as f:
                persuasion_kb = f.read()
        except Exception as e:
            print(f"[GBPSales] Could not load persuasion KB: {e}")

        super().__init__(
            name="gbp_sales",
            role=(
                "the answering-service sales closer who writes proposals, generates Stripe payment links, "
                "and manages the deal pipeline. You are an expert persuader trained in proven sales "
                "psychology. You always lead with the prospect's pain (lost customers), use the "
                "customer's name, give maximum 3 problem points, and make one clear ask. "
                "You never oversell — you let the audit results do the talking.\n\n"
                f"PERSUASION KNOWLEDGE BASE:\n{persuasion_kb}"
            ),
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval,
        )

    async def _create_payment_link(self, business_name: str, amount: float, description: str, link_type: str) -> str:
        """Create a Stripe payment link."""
        try:
            from tools.stripe_tool import create_payment_link, is_configured
            if not is_configured():
                return "[Stripe not configured — add STRIPE_SECRET_KEY to .env]"
            result = create_payment_link(
                amount_dollars=amount,
                description=f"{description} — {business_name}",
                metadata={"business": business_name, "type": link_type},
            )
            return result.get("url") or result.get("error", "Payment link creation failed")
        except Exception as e:
            return f"[Stripe error: {e}]"

    async def _create_deposit_link(self, business_name: str, amount: float) -> str:
        """Create a Stripe payment link for setup payment."""
        return await self._create_payment_link(
            business_name, amount,
            "AI Answering Service Setup", "setup_payment"
        )

    async def _create_split_deposit_link(self, business_name: str) -> str:
        """Create a Stripe payment link for Starter setup as low-friction entry."""
        return await self._create_payment_link(
            business_name, SPLIT_DEPOSIT,
            "AI Answering Service Starter Setup", "starter_setup"
        )

    async def _create_final_invoice(self, business_name: str, email: str, amount: float) -> str:
        """Create a Stripe invoice for final payment."""
        try:
            from tools.stripe_tool import create_invoice, is_configured
            if not is_configured():
                return "[Stripe not configured]"
            if not email or "@" not in email:
                return "[No client email — cannot create invoice automatically]"
            result = create_invoice(
                customer_email=email,
                customer_name=business_name,
                amount_dollars=amount,
                description=f"AI Answering Service — Follow-up Invoice — {business_name}",
                due_days=7,
            )
            return result.get("invoice_url") or result.get("error", "Invoice creation failed")
        except Exception as e:
            return f"[Stripe error: {e}]"

    async def run(self, task: str) -> str:
        self.think(f"Sales Agent (legacy gbp_sales): {task[:100]}")

        task_lower = task.lower()

        # Route to the right action based on task context
        if any(w in task_lower for w in ["final", "delivery", "done", "complete", "invoice", "remainder"]):
            return await self._handle_final_payment(task)
        elif any(w in task_lower for w in ["proposal", "pitch", "close", "send", "prospect"]):
            return await self._handle_proposal(task)
        else:
            # Default: generate proposal from researched prospects
            return await self._handle_proposal(task)

    async def _handle_proposal(self, task: str) -> str:
        """Generate proposals for researched prospects."""
        # Get researched prospects awaiting proposal
        prospects = get_prospects(stage="researched", limit=5)

        output_lines = []

        if prospects:
            self.act(f"Generating proposals for {len(prospects)} prospects")
            for p in prospects:
                biz = p.get("business_name", "Business")
                loc = p.get("location", "")
                email = p.get("email", "")
                issues_raw = p.get("gbp_issues", "[]")
                research = p.get("research_notes", "")

                try:
                    issues = json.loads(issues_raw) if isinstance(issues_raw, str) else issues_raw
                except Exception:
                    issues = []

                # Generate Stripe payment links for each tier setup
                self.think(f"Creating payment links for {biz}")
                starter_link = await self._create_deposit_link(biz, STARTER_SETUP)
                standard_link = await self._create_deposit_link(biz, STANDARD_SETUP)
                pro_link = await self._create_deposit_link(biz, PRO_SETUP)

                # Generate retainer subscription link
                retainer_link = "[Add Stripe key to generate retainer link]"
                try:
                    from tools.stripe_tool import create_subscription_link, is_configured
                    if is_configured():
                        retainer_result = create_subscription_link(
                            RETAINER_PRICE,
                            f"GBP Monthly Management — {biz}"
                        )
                        retainer_link = retainer_result.get("url", retainer_link)
                except Exception as e:
                    print(f"[GBPSales] Stripe retainer link failed for {biz}: {e}")

                # Generate personalized proposal email
                proposal_system = f"""
Write a short, professional proposal email for Katy's AI answering-service offer.

Business: {biz} in {loc}
Their pain points: {', '.join(issues) if issues else 'missed calls / delayed response'}
Research notes: {research[:800] if research else 'N/A'}
Starter setup link ($500): {starter_link}
Standard setup link ($1,000): {standard_link}
Pro setup link ($2,000): {pro_link}

Write in Katy's voice — friendly, direct, not corporate.
Structure:
1. Opening: reference something specific about their business (1 sentence)
2. The problem: what missed-call leakage is costing them in missed jobs/revenue
3. The solution: how AI answering fixes coverage, capture, and follow-up speed
4. Pricing — present all tiers clearly:
    - Starter: $500 setup + $97/month → [STARTER LINK]
    - Standard: $1,000 setup + $197/month → [STANDARD LINK]
    - Pro: $2,000 setup + $297/month → [PRO LINK]
6. CTA: Tell them to pick whichever option works for them — no pressure

Keep it under 275 words. Sound like a real human expert, not a marketing bot.
"""
                proposal = await self.call_llm(proposal_system, f"Write proposal for {biz}")

                # Save to database
                update_prospect(
                    business_name=biz,
                    location=loc,
                    outreach_draft=proposal,
                    stripe_deposit_link=standard_link,
                    pipeline_stage="proposal_ready",
                )

                output_lines.append(f"=== PROPOSAL: {biz} ===")
                output_lines.append(f"Contact: {email or 'email not found — check manually'}")
                output_lines.append(f"Starter setup link ($500): {starter_link}")
                output_lines.append(f"Standard setup link ($1,000): {standard_link}")
                output_lines.append(f"Pro setup link ($2,000): {pro_link}")
                output_lines.append("")
                output_lines.append(proposal)
                output_lines.append("")

        else:
            # Generate proposal from task context (no DB prospects)
            proposal_system = f"""
Based on the context below, write an AI answering-service proposal email.

Pricing must be exact:
- Starter: $500 setup + $97/month
- Standard: $1,000 setup + $197/month
- Pro: $2,000 setup + $297/month

Be specific about their missed-call problems and what fixing call coverage means for their business.
Sound like Katy — direct, warm, expert.
Flag this for approval before sending.

Context: {task}
"""
            proposal = await self.call_llm(proposal_system, task)
            output_lines.append(proposal)

        # Always require approval before sending proposals
        self.needs_approval(
            action="send_answering_service_proposal",
            details={
                "prospects_count": len(prospects) if prospects else 1,
                "starter_setup": STARTER_SETUP,
                "standard_setup": STANDARD_SETUP,
                "pro_setup": PRO_SETUP,
                "preview": output_lines[0][:200] if output_lines else "",
            }
        )

        result = "\n".join(output_lines)
        self.log_task_result(task, result[:300])
        self.act("Proposals ready — awaiting Katy's approval to send")
        return result

    async def _handle_final_payment(self, task: str) -> str:
        """Create final payment invoice after work is delivered."""
        # Get prospects at proposal_sent or deposit_paid stage
        prospects = get_prospects(stage="deposit_paid", limit=10)
        if not prospects:
            prospects = get_prospects(stage="proposal_sent", limit=10)

        if not prospects:
            system = f"""
Generate a professional final payment invoice email.
The setup work has been completed and onboarding is ready.
Request any remaining setup payment and confirm monthly tier billing details.
"""
            return await self.call_llm(system, task)

        output_lines = []

        for p in prospects[:3]:
            biz = p.get("business_name", "")
            email = p.get("email", "")
            loc = p.get("location", "")

            invoice_url = await self._create_final_invoice(biz, email, FINAL_AMOUNT)

            # Update prospect
            update_prospect(
                business_name=biz,
                location=loc,
                stripe_invoice_url=invoice_url,
                pipeline_stage="invoice_sent",
            )

            completion_system = f"""
Write a short, warm completion email to {biz}.
- The answering-service setup is done
- Here's what was completed (list 4-5 deliverables)
- Final payment of ${FINAL_AMOUNT:.0f} is due: {invoice_url}
- Offer to walk them through the changes
- Mention ongoing monthly support if they selected it
- Keep it friendly and brief
"""
            email_body = await self.call_llm(completion_system, f"Completion email for {biz}")

            output_lines.append(f"=== COMPLETION + FINAL INVOICE: {biz} ===")
            output_lines.append(f"Invoice URL: {invoice_url}")
            output_lines.append(f"Send to: {email or 'email needed'}")
            output_lines.append("")
            output_lines.append(email_body)
            output_lines.append("")

        self.needs_approval(
            action="send_completion_and_invoice",
            details={"count": len(prospects), "final_amount": FINAL_AMOUNT}
        )

        return "\n".join(output_lines)

