import json
import re
from .base import BaseAgent

VALID_AGENTS = [
    "gbp_scout", "gbp_researcher", "gbp_sales",
    "outreach", "sales", "sales_ops",
    "small_biz_expert", "research", "research_assistant", "engineer",
    "team_leader", "job_seeker", "scout", "networking", "coach",
    "lead_gen", "marketing", "biz_dev", "automations",
    "solutions_architect", "resume_builder", "interview_coach",
]

class CoordinatorAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval, dispatch_fn=None):
        super().__init__(
            name="coordinator",
            role="the team leader who routes tasks to the right specialist agents and synthesizes their findings for Katy",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )
        # dispatch_fn: async (agent_names: list, task: str) -> dict
        self.dispatch_fn = dispatch_fn

    def _extract_agents(self, llm_response: str) -> list:
        """Parse agent names from LLM response. Expects a JSON block like:
        {"agents": ["scout", "outreach"]}
        Falls back to scanning text for known agent names.
        """
        # Try JSON block first
        match = re.search(r'\{[^}]*"agents"\s*:\s*\[[^\]]*\][^}]*\}', llm_response, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                names = [n for n in data.get("agents", []) if n in VALID_AGENTS]
                if names:
                    return names
            except (json.JSONDecodeError, KeyError):
                pass

        # Fallback: scan for any valid agent names mentioned in the response
        found = [name for name in VALID_AGENTS if re.search(rf'\b{name}\b', llm_response, re.IGNORECASE)]
        return found

    async def handle_message(self, message: str) -> str:
        """
        Swarm-style: ask LLM which agents to run, then actually run them.
        Returns a synthesized response from all agent results.
        """
        self.think(f"Routing message: {message}")

        routing_system = f"""
You are the coordinator for Katy's elite GBP sales crew. One mission: find local businesses
with broken Google Business Profiles and close them as paying clients ($197/each).

When Katy sends a message, pick the right agents (1-3 max) and end with JSON on the last line.

Valid agents: {', '.join(VALID_AGENTS)}

THE CREW:
- gbp_scout: hits Google Maps, finds businesses with missing/broken GBPs, scores them HOT/WARM
- gbp_researcher: digs into each prospect — finds owner name, email, phone, website intel, builds pitch dossier
- gbp_sales: writes the proposal, generates Stripe payment link ($197 full or $98 split deposit), handles the close
- outreach: writes killer cold emails and DMs — short, specific, human — queues for Katy approval
- sales: handles objections, follow-ups, rebuttals — knows every excuse a small biz owner uses
- sales_ops: tracks the pipeline, logs who was contacted, flags who needs follow-up
- small_biz_expert: knows exactly what keeps small business owners up at night — speaks their language
- research: deep intel on a specific business, owner, or market
- engineer: fixes code, technical issues only

ROUTING RULES:
- "find prospects / scan / search" → gbp_scout, gbp_researcher, outreach
- "follow up / check pipeline" → sales_ops, sales
- "write email / draft message" → outreach
- "send proposal / close deal" → gbp_sales
- "objection / rebuttal / they said no" → sales, small_biz_expert
- anything technical → engineer

End with JSON: {{"agents": ["name1", "name2"]}}
"""
        routing_response = await self.call_llm(routing_system, message)
        agent_names = self._extract_agents(routing_response)

        # Strip the JSON line from the explanation shown to Katy
        explanation = re.sub(r'\{[^}]*"agents"[^}]*\}\s*$', '', routing_response).strip()

        if not agent_names:
            # Coordinator can handle it directly
            self.act("Handling directly — no sub-agents needed")
            return explanation or routing_response

        if not self.dispatch_fn:
            # No dispatcher wired in — just return the plan
            self.act("No dispatch_fn configured; returning plan only")
            return routing_response

        self.act(f"Dispatching to: {', '.join(agent_names)}")
        results = await self.dispatch_fn(agent_names, message)

        # Synthesize all results into a final response
        synthesis_input = (
            f"Katy asked: {message}\n\n"
            + "\n\n".join(f"[{name}]\n{result}" for name, result in results.items())
        )
        synthesis_system = """
Synthesize the agent results into a clear, direct update for Katy.
- Lead with the most important findings
- Be specific — names, numbers, links where available
- Flag anything awaiting her approval
- Keep it concise
"""
        summary = await self.call_llm(synthesis_system, synthesis_input)
        self.act("Synthesis complete")
        return summary

    async def run(self, task: str) -> str:
        """
        Direct task mode: decide which agents to run, dispatch them, return synthesis.
        """
        self.think(f"Coordinator planning task: {task}")

        routing_system = f"""
Break this task into agent assignments. Pick the right agents from: {', '.join(VALID_AGENTS)}
Respond with a brief plan then end with JSON: {{"agents": ["name1", "name2"]}}
"""
        plan = await self.call_llm(routing_system, task)
        agent_names = self._extract_agents(plan)

        if not agent_names or not self.dispatch_fn:
            self.act(f"Plan created (no dispatch): {task[:50]}")
            return plan

        self.act(f"Dispatching task to: {', '.join(agent_names)}")
        results = await self.dispatch_fn(agent_names, task)

        synthesis_input = (
            f"Task: {task}\n\n"
            + "\n\n".join(f"[{name}]\n{result}" for name, result in results.items())
        )
        synthesis_system = "Summarize these agent results into a concise action report for Katy."
        return await self.call_llm(synthesis_system, synthesis_input)
