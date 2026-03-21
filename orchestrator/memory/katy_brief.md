# Katy's Agent Knowledge Base
> This file is the source of truth for all agents. Read this before every task.
> Last updated: March 2026

---

## Who I am

**Full name:** Kathleen Louise Casto - goes by Katy  
**Age:** 40  
**Location:** Belle / Charleston, WV area  
**Family:** Husband Joey (Joseph Brandon Casto, 41), daughter Ariel Lynne Hancock (16)  
**School:** Maestro College (online AAS, AI Software Engineering) - currently enrolled, early stages of formal coding  
**Background:** 10+ years digital marketing (self-taught, no degree)  
**Development style:** Vibe coder - I direct AI tools to build applications, identify problems, find solutions, and iterate fast. I never give up.

---

## My story (use this for cover letters and outreach tone)

I spent years trying to break into digital marketing with no luck - everyone wants experience but won't give you a chance to get it. When Bolt and Replit launched I realized I could BUILD my way in. My first project was MarketSim, a hands-on digital marketing learning platform with simulations and workshops. I lost everything mid-build when I ran out of money - but I didn't stop. I found Maestro AI College, enrolled in AI Software Engineering, and have been building ever since. Every project teaches me something new. I build real things, ship them, and keep going.

---

## Skills

### Technical
- **Languages:** JavaScript, TypeScript, Python (learning - loops, functions, list/dict operations)
- **Frontend:** React, HTML, CSS, Tailwind
- **Backend / Database:** Supabase, Node.js, FastAPI basics
- **AI / APIs:** Claude API (Anthropic), Gemini API, OpenAI API, ElevenLabs (voice), Deepgram (speech-to-text), Runway (video gen)
- **Dev tools:** GitHub (katycat1313), Netlify (deploy), Replit, Bolt, VS Code
- **Automation:** n8n, Zapier
- **No-code:** Bubble, FlutterFlow
- **Hardware:** Creality K1C 3D printer, RC cars, Mac M4 (primary), Asus Zephyrus G14 (agent machine)

### Non-technical
- Digital marketing strategy (10+ years)
- Customer onboarding and implementation thinking
- Product ideation and problem framing
- Persistent problem-solving under pressure
- AI-assisted development and prompt engineering
- Communication: direct, warm, action-oriented

---

## Projects I've built

### CCPractice / Resonatr ⭐ (strongest portfolio piece)
AI-powered sales training and cold call coaching platform with real-time voice feedback.  
**Stack:** React, TypeScript, Deepgram (speech-to-text), Google TTS, Gemini API, ReactFlow  
**What it does:** Live call simulation, AI scores your pitch in real time, coaching feedback  
**Status:** Most technically complete project - deployed and working  
**Pitch:** "I built a real-time AI coach that listens to sales calls and gives live feedback - think Gong but for training"

### MarketSim
Digital marketing learning platform with hands-on workshops, AI mentor, Stripe payments, gamification.  
**Stack:** React, Supabase, Stripe, AI mentor integration  
**Status:** Discontinued (hosting costs) - but fully built and functional while live  
**Pitch:** "Built a full ed-tech platform from scratch, including payments and gamified learning flows"

### Smart Intake Solutions
Automated contractor intake form system - deployed at smartintakesolutions.space  
**Stack:** React, Netlify, form automation  
**What it does:** Replaces manual contractor intake with smart automated forms  
**Status:** Deployed and live  
**Pitch:** "Shipped a B2B automation tool for contractors and deployed it to a live domain"

### RawBlockAI (in progress)
Multi-agent pipeline that automatically generates B-roll footage from prompts - researches subjects and produces targeted video clips ready for editing.  
**Stack:** Docker, multi-agent orchestration (5-6 agents), Runway API, React  
**Status:** Successfully generating videos - currently refactoring to clean up code smells and tighten the pipeline specifically around B-roll prompt targeting  
**Pitch:** "Built a multi-agent AI pipeline that auto-generates B-roll footage using Runway - it's generating real video, I'm now hardening the codebase"

### ConversionFlow AI / GadgetsandThose
Affiliate marketing and content generation tools.  
**Stack:** AI content generation, affiliate integration  
**Status:** Experimental

---

## What I'm looking for

### Target roles (in order of fit)
1. **AI Application Developer / Junior AI Engineer** - building apps and features using AI APIs
2. **Solutions Implementation Specialist** - onboarding customers, getting them set up and running
3. **AI Product Manager** - directing what gets built and why
4. **QA / AI Evaluator** - testing AI systems, finding edge cases
5. **VA / Executive Assistant** - only if pay justifies it

### Target pay
- Hourly: $35/hr minimum
- Salary: $50,000 – $60,000/year
- Open to remote, contract, or full-time

### What I bring that's rare
- I actually ship things - not just tutorials, real deployed apps
- I can work with AI APIs that most junior devs have never touched
- 10 years of marketing brain means I understand the user, not just the code
- I learn fast and I don't stop when it gets hard

### What I won't do
- Unpaid trials or spec work
- Roles below $30/hr
- Positions that are pure data entry with no growth path

---

## My voice and communication style

Use these as tone anchors when writing on my behalf:

- Direct and real - no corporate fluff
- Warm but confident - I know what I bring
- Storyteller - I lead with the journey, not just the outcome
- Honest about being early-stage but clear about what I've done
- I say "I built" not "I assisted in building" - I directed it, I own it

**Sample phrases in my voice:**
- "I'm still early in my formal coding journey but I've shipped real things"
- "I learn by building - every project teaches me something new"
- "I never give up - that's not a platitude, it's literally how I got here"
- "I directed the AI to build it, debugged it, deployed it - it's mine"

---

## Important context for job search agents

- Katy is transitioning careers at 40 - frame this as an asset (real-world experience + new skills) not a liability
- She has no CS degree - lead with shipped projects and AI API experience instead
- Her strongest differentiator is that she builds AI-integrated apps, not just websites
- CCPractice/Resonatr is the strongest portfolio piece - always mention it first
- She is enrolled in an accredited AAS program - this counts as current education
- Target companies: AI startups, SaaS companies, agencies doing AI implementation, tech-forward SMBs
- Best platforms to search: Wellfound (AngelList), LinkedIn, Contra, Toptal, Deel, Remote.co

---

## Approved outreach behaviors (no approval needed)
- Search job boards and compile listings
- Research recruiters and companies
- Draft outreach messages (do not send without approval)
- Connect requests on LinkedIn (draft only - do not send without approval)
- Summarize findings and report to Katy

## Always requires Katy's approval before acting
- Sending any email or message
- Submitting any job application
- Posting anything publicly
- Signing up for any service or platform
- Any financial transaction

---

## Common bottlenecks and how Katy solves them
> Agents use this section to help Katy debug, advise on projects, and demonstrate problem-solving in interviews

### API and integration bottlenecks
| Symptom | Likely cause | Solution pattern |
|---|---|---|
| API calls randomly failing | Rate limiting or missing retry logic | Add exponential backoff + error boundaries |
| Response slow or times out | No streaming, synchronous calls | Switch to streaming, use async/await |
| Costs exploding | No token limits, no caching | Add max_tokens, cache repeated prompts |
| Wrong data returned | Prompt too vague, no output structure | Add JSON schema to prompt, validate output |
| Works locally, breaks in prod | Env vars not set, CORS, wrong URLs | Check .env, add CORS headers, use relative URLs |

### Multi-agent bottlenecks
| Symptom | Likely cause | Solution pattern |
|---|---|---|
| Agents looping or stuck | No exit condition, unclear task scope | Add explicit done states, limit max iterations |
| Agents contradicting each other | No shared context or memory | Shared knowledge base, message bus |
| Agent ignores instructions | System prompt too long or conflicting | Shorten prompt, put critical rules at top AND bottom |
| Pipeline stalls at one step | Agent waiting for input that never comes | Add timeouts and fallback defaults |
| Output quality degrades mid-pipeline | Context window filling up | Summarize earlier steps, never pass full history |

### React and frontend bottlenecks
| Symptom | Likely cause | Solution pattern |
|---|---|---|
| Infinite re-renders | useEffect dependency array wrong | Audit deps, use useCallback/useMemo |
| State not updating | Mutating state directly | Always return new object/array, never mutate |
| Slow UI | Re-rendering whole tree | Lift state down, use React.memo |
| Works on desktop, breaks mobile | No responsive design | Add Tailwind breakpoints, test at 375px |

### Supabase bottlenecks
| Symptom | Likely cause | Solution pattern |
|---|---|---|
| Auth not persisting | Session not being stored | Check persistSession: true in client config |
| Slow queries | No indexes, fetching too many columns | Add indexes, use select('only,needed,cols') |
| RLS blocking everything | Row Level Security policy too strict | Check policies in Supabase dashboard |

### Code smell patterns Katy identifies and fixes
- Duplicated logic → extract to a shared function
- Magic numbers (if x > 47) → name them as constants
- Functions doing 5 things → split into single-responsibility functions
- Dead/old code left in → delete it, git has the history
- No error handling → wrap in try/catch with meaningful messages
- Hardcoded API keys in code → move to .env immediately

---

## Portfolio gap analysis and target projects
> Agents use this to advise Katy on what to build next to maximize hiring chances

### What the portfolio already proves
- Can build and ship full-stack AI apps (CCPractice/Resonatr)
- Understands multi-agent architecture (RawBlockAI)
- Can deploy to production (Smart Intake, CCPractice)
- Knows multiple AI APIs: Claude, Gemini, ElevenLabs, Runway, Deepgram

### What is missing for top target roles

For AI Application Developer roles:
- A clean well-documented public GitHub repo - recruiters look at actual code
- One project using a vector database (Pinecone or pgvector in Supabase) - shows RAG knowledge
- One project with visible agent reasoning/thought log - shows she understands agent internals

For Solutions Implementation roles:
- A 2-3 min Loom demo video of at least one app - implementation specialists sell and demo
- A proper README with setup steps, screenshots, and architecture summary for one project

For any role:
- LinkedIn with projects linked and title set to "AI Application Developer"
- A simple portfolio site listing all projects with links and one-paragraph descriptions

### Needle-in-haystack project ideas (high signal, low competition)
1. AI interview coach (voice) - user speaks answers, AI scores them live. Uses Deepgram + Claude. She already has this exact stack from CCPractice.
2. RAG over your own resume - paste a job description, AI tells you how to tailor your resume. Uses pgvector + Claude. Simple, useful, shows RAG skills.
3. Agent activity spy dashboard - literally what she is building now. Document and showcase it. This IS the needle-in-haystack project.
4. AI onboarding flow builder - given a SaaS description, generates a step-by-step customer onboarding checklist. Directly relevant to implementations roles.
5. Cold outreach personalizer - paste a LinkedIn profile URL, get a personalized first message drafted. Shows Claude API + prompt engineering. Useful and shareable.
