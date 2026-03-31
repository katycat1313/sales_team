# Agent Architecture Summary

## 1. Base Class Pattern

All agents inherit from `BaseAgent` ([base.py](orchestrator/agents/base.py)) which provides:

### Constructor Pattern
```python
def __init__(self, name: str, role: str, katy_brief: str, log_event: Callable, request_approval: Callable)
```

Every agent calls:
```python
super().__init__(
    name="agent_name",
    role="descriptive role and responsibilities",
    katy_brief=katy_brief,
    log_event=log_event,
    request_approval=request_approval
)
```

**Example** (SalesAgent):
```python
super().__init__(
    name="sales",
    role="the sales specialist who helps Katy close deals...",
    katy_brief=katy_brief,
    log_event=log_event,
    request_approval=request_approval
)
```

---

## 2. Core Methods in BaseAgent

### LLM Interaction
- **`async def call_llm(system_prompt: str, user_message: str) -> str`**
  - Routes through Vertex AI (production) with Gemini API fallback
  - Automatically includes agent's memory context and Katy brief
  - Used by: all agents

### Memory Operations
- **`remember(key: str, value: str)`** — Store agent-specific persistent fact
- **`recall(key: str)`** — Retrieve single fact
- **`recall_all()`** — Get all agent's memories
- **`note(content: str, category: str = "general")`** — Add timestamped note
- **`get_notes(category: str = None)`** — Retrieve notes by category
- **`log_task_result(task: str, result: str)`** — Log task completion
- **`think(thought: str)`** — Log internal reasoning (event type = "thought")
- **`act(action: str)`** — Log actions taken (event type = "action")

### Approval Gates
- **`needs_approval(action: str, details: dict)`** — Request Katy's approval before sensitive actions (sending messages, publishing content, proposals)

---

## 3. Agent Execution Pattern

Every agent implements:
```python
async def run(self, task: str) -> str:
    self.think(f"[descriptive thought about task]")
    
    system = """[Task-specific system prompt]"""
    result = await self.call_llm(system, task)
    
    self.log_task_result(task, result[:200])
    
    # Optional: approval gates
    if "sensitive_action" in task.lower():
        self.needs_approval("action_name", {"preview": result[:300]})
    
    return result
```

---

## 4. Current Agents (23 total)

### Core Sales Pipeline
| Agent | Role | Tools Used |
|-------|------|-----------|
| **gbp_scout** | Finds local businesses with incomplete Google Business Profiles | `gbp_audit.run_prospect_scan()` |
| **gbp_researcher** | Builds intel dossiers on prospects; browses websites, extracts contact info | `browser_tool`, `gbp_audit` |
| **gbp_sales** | Writes proposals, generates payment links, manages deal closure | `stripe_tool` (payment/invoice links) |
| **outreach** | Drafts personalized cold emails and DMs | `browser_tool`, `gmail_tool.send_email()` |

### Core Service Agents
| Agent | Role | Tools Used |
|-------|------|-----------|
| **sales** | Crafts pitches, writes proposals for freelance/service contracts | None (LLM only) |
| **sales_ops** | Tracks pipeline, monitors deal status, flags stalled leads | None (LLM only) |
| **marketing** | Positions services, crafts content (requires Katy approval before posting) | None (LLM only) |
| **lead_gen** | Identifies and qualifies high-potential prospect niches | None (LLM only) |
| **research** | Deep investigation: companies, markets, people, opportunities | None (LLM only) |
| **engineer** | Debugs code, reviews architecture, writes snippets | None (LLM only) |

### Specialized Agents
| Agent | Role | Tools Used |
|-------|------|-----------|
| **biz_dev** | Builds partnerships, identifies joint ventures | None |
| **coach** | Interview/performance coaching | None |
| **interview_coach** | Prepares candidates for technical interviews | None |
| **job_seeker** | Job hunting strategy and application support | None |
| **networking** | Networking strategy and outreach planning | None |
| **research_assistant** | Supporting research tasks | None |
| **resume_builder** | Resume writing and optimization | None |
| **scout** | General prospect finding (deprecated/legacy) | None |
| **small_biz_expert** | Small business advisory | None |
| **solutions_architect** | Systems design and architecture planning | None |
| **team_leader** | Team management and coordination | None |
| **coordinator** | Orchestrates multi-agent workflows | None |
| **automations** | Automation workflow creation | None |

---

## 5. Tool Integration

### Tools Available in `/tools/`
1. **stripe_tool.py** — Payment link creation (`create_payment_link()`, `create_invoice()`, `create_subscription_link()`)
2. **gmail_tool.py** — Email sending via SendGrid (`send_email()`)
3. **browser_tool.py** — Website browsing (`browser_tool.general_browse()`)
4. **gbp_audit.py** — Google Business Profile scanning (`run_prospect_scan()`, `audit_gbp()`)
5. **vapi_tool.py** — Voice API integration
6. **google_calendar_tool.py** — Calendar management
7. **sheets_tool.py** — Google Sheets operations
8. **sms_tool.py** — SMS sending
9. **gmail_tool.py** — Email operations

### Tool Import Pattern
Tools are **conditionally imported** within methods (not at module level) to:
- Avoid errors if tools aren't configured
- Keep agent code clean
- Allow runtime configuration checks

**Example** (gbp_sales.py):
```python
async def _create_payment_link(self, business_name: str, amount: float, description: str, link_type: str) -> str:
    try:
        from tools.stripe_tool import create_payment_link, is_configured
        if not is_configured():
            return "[Stripe not configured — add STRIPE_SECRET_KEY to .env]"
        result = create_payment_link(...)
        return result.get("url") or result.get("error")
    except Exception as e:
        return f"[Stripe error: {e}]"
```

### Tool Usage by Agent
| Agent | Tool | Function |
|-------|------|----------|
| gbp_scout | gbp_audit | `run_prospect_scan(niche, location, limit=15)` |
| gbp_researcher | browser_tool | `browser_tool.general_browse(url)` |
| gbp_researcher | gbp_audit | `audit_gbp(business_name, location)` |
| gbp_sales | stripe_tool | `create_payment_link()`, `create_invoice()`, `create_subscription_link()` |
| outreach | browser_tool | Website content retrieval |
| outreach | gmail_tool | `send_email(to, subject, body)` |

---

## 6. Prospect & Memory Interaction

### Prospect Database (SQLite)
Located in `/orchestrator/memory/agent_memory.db`

**Memory Module Functions** (from `memory.memory`):
- **`save_prospect(business_name, location, niche, phone, website, gbp_score, gbp_issues, priority, audit_data, pipeline_stage)`** — Save new prospect
- **`get_prospects(stage="found", limit=100)`** — Retrieve prospects by pipeline stage
- **`update_prospect(business_name, location, **updates)`** — Update prospect record
- **`save_contact()`, `get_contacts()`, `contact_exists()`, `mark_contacted()`** — Contact tracking

### Pipeline Stages
```
found → researched → contacted → responded → proposal_sent → negotiating → closed_won/lost
```

**Example Flow**:
1. **gbp_scout** finds prospects → saves with `stage="found"`
2. **gbp_researcher** retrieves `stage="found"` → researches → updates to `stage="researched"`
3. **outreach** gets researched prospects → sends emails → updates contact status
4. **gbp_sales** tracks deal progression through remaining stages

### Agent Memory Storage
Each agent has isolated memory via SQLite tables:
- **facts** — Key-value store (agent-specific)
- **jobs** — Job listings (shared)
- **contacts** — Contacts found during outreach (shared)
- **tasks** — Task history and results
- **approvals** — Record of Katy's approval/rejection decisions
- **notes** — Free-form notes by category

**Usage**:
```python
# Store
self.remember("gbp_scan_1_cities", "Austin, Dallas, Houston")

# Retrieve
contacts = self.recall_all()

# Add notes
self.note("High-priority plumber lead in Austin", category="lead_pipeline")

# Get categorical notes
pipeline_notes = self.get_notes(category="lead_pipeline")
```

---

## 7. Shared Patterns

### System Prompt Strategy
Each agent has a **role-specific system prompt** that includes:
1. **Agent identity** — Who they are and what they do
2. **Approval requirements** — Actions that need Katy sign-off
3. **Katy's core offers** — What to sell (AI answering service tiers: $97-$297/mo)
4. **Output format** — How to structure results (JSON blocks, structured text, etc.)
5. **Persuasion KB** — Some agents (outreach, gbp_sales) load `persuasion_techniques.md`

**Example** (outreach agent):
```python
system = f"""
You are writing a cold outreach email FROM Katy...
Offer tiers:
- Starter: $500 setup + $97/month
- Standard: $1,000 setup + $197/month
- Pro: $2,000 setup + $297/month

Write a SHORT, friendly cold email...
Output EXACTLY in this format:
TO: ...
SUBJECT: ...
BODY: ...
"""
```

### Logging Pattern
All agents log events through:
- **`self.think()`** → Internal reasoning (not sent to user)
- **`self.act()`** → Actions taken (logged to event stream)
- **`self.log_task_result(task, result[:200])`** → Task completion with preview
- **`self.note()`** → Persistent notes for future reference

### Approval Gates
Agents request approval for:
- Sending proposals or emails
- Publishing content (social/website)
- Creating payment links
- Spending money (ads, tool credits)

---

## 8. Initialization Context

Every agent receives:
1. **katy_brief** — Markdown file with Katy's background, projects, skills, offering
2. **log_event** — Callback to log agent actions/thoughts
3. **request_approval** — Callback for approval gates

These are passed from the orchestrator (main.py) and enable:
- Agents to contextualize decisions using Katy's real background
- Centralized logging and audit trail
- Human-in-the-loop control for risky actions

---

## Summary: Common Structure

```python
from .base import BaseAgent
from memory.memory import get_prospects, update_prospect

class [Agent]Agent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="[agent_name]",
            role="[clear role description with specific responsibilities]",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )

    async def run(self, task: str) -> str:
        self.think(f"[descriptive thought]")
        
        system = """[Task-specific system prompt with:
        - Clear identity
        - Output format requirements
        - Approval gates
        - Katy's offerings/context]"""
        
        result = await self.call_llm(system, task)
        
        self.log_task_result(task, result[:200])
        
        # Optional: conditional approval
        if "sensitive_action" in task.lower():
            self.needs_approval("action_type", {"details": result[:300]})
        
        return result
```

---

## Key Takeaways

✅ **All agents inherit from BaseAgent** — Consistent interface, memory, LLM routing
✅ **Async execution** — All agents use `async def run()` method
✅ **Conditional tool imports** — Tools imported at runtime within methods
✅ **SQLite memory backend** — Persistent agent memory + shared prospect database
✅ **Approval gates** — Critical actions require Katy approval before execution
✅ **Structured logging** — Actions, thoughts, tasks all logged to event stream
✅ **Pipeline stages** — Prospects move through defined stages (found → closed)
✅ **Shared context** — All agents aware of Katy's offerings, background, and current pipeline

