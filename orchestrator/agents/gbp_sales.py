"""
GBP Sales Agent
---------------
Handles the pitch, proposal, and payment side of GBP service sales.

Responsibilities:
- Generates personalized proposals with specific GBP fixes
- Creates Stripe deposit payment link (50% upfront)
- Creates Stripe invoice for final payment (50% on delivery)
- Offers monthly retainer as upsell ($97/month)
- Notifies Katy when deposits land (via Telegram)

Pricing:
- Free automated GBP audit (lead magnet)
- $197 one-time GBP optimization (deposit: ~$99 upfront)
- $97/month ongoing management (optional retainer upsell)
"""

from .base import BaseAgent
from memory.memory import get_prospects, update_prospect


DEPOSIT_PERCENT = 0.50
OPTIMIZATION_PRICE = 197.00
RETAINER_PRICE = 97.00


class GBPSalesAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        # Load persuasion knowledge base
        persuasion_kb = ""
        try:
            import os
            kb_path = os.path.join(os.path.dirname(__file__), "../memory/persuasion_techniques.md")
            with open(kb_path, "r") as f:
                persuasion_kb = f.read()
        except Exception:
            pass

        super().__init__(
            name="gbp_sales",
            role=(
                "the GBP service sales closer who writes proposals, generates Stripe payment links, "
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

    async def _create_deposit_link(self, business_name: str, amount: float) -> str:
        """Create a Stripe payment link for the deposit."""
        try:
            from tools.stripe_tool import create_payment_link, is_configured
            if not is_configured():
                return "[Stripe not configured — add STRIPE_SECRET_KEY to .env]"
            result = create_payment_link(
                amount_dollars=amount,
                description=f"GBP Optimization Deposit — {business_name}",
                metadata={"business": business_name, "type": "gbp_deposit"},
            )
            return result.get("url") or result.get("error", "Payment link creation failed")
        except Exception as e:
            return f"[Stripe error: {e}]"

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
                description=f"GBP Optimization — Final Payment — {business_name}",
                due_days=7,
            )
            return result.get("invoice_url") or result.get("error", "Invoice creation failed")
        except Exception as e:
            return f"[Stripe error: {e}]"

    async def run(self, task: str) -> str:
        self.think(f"GBP Sales Agent: {task[:100]}")

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

        deposit_amount = round(OPTIMIZATION_PRICE * DEPOSIT_PERCENT, 2)
        final_amount = OPTIMIZATION_PRICE - deposit_amount

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
                    import json
                    issues = json.loads(issues_raw) if isinstance(issues_raw, str) else issues_raw
                except Exception:
                    issues = []

                # Generate Stripe deposit link
                self.think(f"Creating deposit link for {biz}")
                deposit_link = await self._create_deposit_link(biz, deposit_amount)

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
                except Exception:
                    pass

                # Generate personalized proposal email
                proposal_system = f"""
Write a short, professional proposal email for a GBP optimization service.

Business: {biz} in {loc}
Their GBP issues: {', '.join(issues) if issues else 'Multiple gaps'}
Research notes: {research[:800] if research else 'N/A'}
Deposit link: {deposit_link}
Retainer link: {retainer_link}

Write in Katy's voice — friendly, direct, not corporate.
Structure:
1. Opening: reference something specific about their business (1 sentence)
2. The problem: what their GBP gaps are costing them in missed customers (specific, urgent)
3. The solution: what you'll fix exactly (3-5 bullet points of deliverables)
4. Pricing: $197 total — ${deposit_amount:.0f} deposit to start, ${final_amount:.0f} on completion
5. Upsell: Optional $97/month ongoing management (handles reviews, posts, updates)
6. CTA: Click the deposit link to get started → [DEPOSIT LINK]
7. Optional retainer: [RETAINER LINK]

Keep it under 250 words. Sound like a real human expert, not a marketing bot.
"""
                proposal = await self.call_claude(proposal_system, f"Write proposal for {biz}")

                # Save to database
                update_prospect(
                    business_name=biz,
                    location=loc,
                    outreach_draft=proposal,
                    stripe_deposit_link=deposit_link,
                    pipeline_stage="proposal_ready",
                )

                output_lines.append(f"=== PROPOSAL: {biz} ===")
                output_lines.append(f"Contact: {email or 'email not found — check manually'}")
                output_lines.append(f"Deposit link: {deposit_link}")
                output_lines.append(f"Retainer link: {retainer_link}")
                output_lines.append("")
                output_lines.append(proposal)
                output_lines.append("")

        else:
            # Generate proposal from task context (no DB prospects)
            proposal_system = f"""
Based on the context below, write a GBP optimization proposal email.
Pricing: ${OPTIMIZATION_PRICE} total — ${deposit_amount:.0f} deposit, ${final_amount:.0f} on delivery
Also mention: ${RETAINER_PRICE}/month ongoing management option.

Be specific about their GBP problems and what fixing it means for their business.
Sound like Katy — direct, warm, expert.
Flag this for approval before sending.

Context: {task}
"""
            proposal = await self.call_claude(proposal_system, task)
            output_lines.append(proposal)

        # Always require approval before sending proposals
        self.needs_approval(
            action="send_gbp_proposal",
            details={
                "prospects_count": len(prospects) if prospects else 1,
                "deposit_amount": deposit_amount,
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
            system = """
Generate a professional final payment invoice email.
The work has been completed. Request the remaining 50% payment.
Mention what was delivered.
"""
            return await self.call_claude(system, task)

        output_lines = []
        final_amount = OPTIMIZATION_PRICE - round(OPTIMIZATION_PRICE * DEPOSIT_PERCENT, 2)

        for p in prospects[:3]:
            biz = p.get("business_name", "")
            email = p.get("email", "")
            loc = p.get("location", "")

            invoice_url = await self._create_final_invoice(biz, email, final_amount)

            # Update prospect
            update_prospect(
                business_name=biz,
                location=loc,
                stripe_invoice_url=invoice_url,
                pipeline_stage="invoice_sent",
            )

            completion_system = f"""
Write a short, warm completion email to {biz}.
- The GBP optimization is done
- Here's what was completed (list 4-5 deliverables)
- Final payment of ${final_amount:.0f} is due: {invoice_url}
- Offer to walk them through the changes
- Mention the ${RETAINER_PRICE}/month ongoing management option
- Keep it friendly and brief
"""
            email_body = await self.call_claude(completion_system, f"Completion email for {biz}")

            output_lines.append(f"=== COMPLETION + FINAL INVOICE: {biz} ===")
            output_lines.append(f"Invoice URL: {invoice_url}")
            output_lines.append(f"Send to: {email or 'email needed'}")
            output_lines.append("")
            output_lines.append(email_body)
            output_lines.append("")

        self.needs_approval(
            action="send_completion_and_invoice",
            details={"count": len(prospects), "final_amount": final_amount}
        )

        return "\n".join(output_lines)
