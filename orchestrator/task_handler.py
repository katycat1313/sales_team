"""
TaskHandler — Swarm-style multi-agent orchestration.

Dispatch agents in sequence, chaining each agent's output as context
into the next agent's input, exactly like OpenAI Swarm handoffs.
"""

import asyncio


class TaskHandler:
    def __init__(self, agent_map: dict, katy_brief: str, log_event, request_approval):
        self.agent_map = agent_map
        self.katy_brief = katy_brief
        self.log_event = log_event
        self.request_approval = request_approval

    def _make_agent(self, name: str):
        factory = self.agent_map.get(name)
        if not factory:
            return None
        return factory(self.katy_brief, self.log_event, self.request_approval)

    async def run_agent(self, name: str, task: str) -> str:
        """Run a single named agent and return its result."""
        agent = self._make_agent(name)
        if not agent:
            msg = f"Agent '{name}' not found in agent map."
            self.log_event("task_handler", "result", msg)
            return msg
        self.log_event(name, "thought", f"Dispatched by coordinator: {task[:100]}")
        try:
            result = await agent.run(task)
            self.log_event(name, "result", result[:400])
            return result
        except Exception as exc:
            err = f"[{name} error] {str(exc)}"
            self.log_event(name, "result", err)
            return err

    async def dispatch(self, agent_names: list, initial_task: str) -> dict:
        """
        Run agents in sequence, chaining outputs (Swarm-style handoff).
        Each agent receives the original task PLUS all prior agents' findings.
        """
        results = {}
        context = initial_task

        for name in agent_names:
            self.log_event("task_handler", "action", f"Handing off to → {name}")
            result = await self.run_agent(name, context)
            results[name] = result

            # Chain: next agent gets original task + accumulated findings
            prior = "\n\n".join(
                f"[{n} findings]\n{r}" for n, r in results.items()
            )
            context = f"Original task: {initial_task}\n\n{prior}"

        return results

    async def dispatch_parallel(self, agent_names: list, task: str) -> dict:
        """Run agents in parallel (no chaining) — useful for independent lookups."""
        results = await asyncio.gather(
            *[self.run_agent(name, task) for name in agent_names],
            return_exceptions=True
        )
        return {
            name: (str(r) if isinstance(r, Exception) else r)
            for name, r in zip(agent_names, results)
        }
