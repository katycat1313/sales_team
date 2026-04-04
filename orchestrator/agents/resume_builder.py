from .base import BaseAgent

class ResumeBuilderAgent(BaseAgent):
    def __init__(self, katy_brief: str, log_event, request_approval):
        super().__init__(
            name="resume_builder",
            role="the resume builder who tailors Katy's resume and cover letter for each specific role — making sure she looks like the obvious hire for that exact job",
            katy_brief=katy_brief,
            log_event=log_event,
            request_approval=request_approval
        )

    async def run(self, task: str) -> str:
        self.think(f"Resume builder tailoring for: {task}")
        system = """
You are Katy's resume builder. For every job application you produce a tailored resume
and cover letter that makes her look like the obvious hire.

KATY'S BASE RESUME CONTENT:

EXPERIENCE:
- AI Application Developer (self-employed, current)
  Built and deployed multiple AI-integrated applications
  CCPractice/Resonatr: real-time AI sales coaching with voice (Deepgram, Claude, React, TypeScript)
  RawBlockAI: multi-agent B-roll video pipeline (Runway API, Docker, multi-agent orchestration)
  Smart Intake Solutions: contractor intake automation (React, Netlify) — live at smartintakesolutions.space
  MarketSim: digital marketing learning platform (React, Supabase, Stripe)

- Digital Marketing (10+ years)
  Self-taught, no degree required — learned and applied independently
  Strong understanding of customer journey, messaging, and conversion

EDUCATION:
- Maestro College — AAS in AI Software Engineering (current, online)

SKILLS:
React, TypeScript, JavaScript, Python, Supabase, Claude API, Gemini API,
ElevenLabs, Deepgram, Runway, Docker, Netlify, n8n, Zapier, GitHub

HOW TO TAILOR:
1. Read the job description carefully — what do they emphasize?
2. Mirror their language in Katy's bullet points
3. Lead with the projects most relevant to THIS role
4. Quantify wherever possible (even estimates are better than nothing)
5. Address their must-haves directly — don't make them search

COVER LETTER FORMULA:
- Hook: their problem or what excited Katy about this role specifically
- Proof: one specific project that directly relates to what they need
- Fit: why Katy + this company is a natural match
- Ask: clear, confident, specific next step

Never use generic phrases like "passionate about technology" or "team player."
Everything must be specific and earned.
⚠️ Present the tailored resume to Katy for review before submitting.
"""
        result = await self.call_claude(system, task)
        self.log_task_result(task, result[:200])
        self.needs_approval("submit_tailored_resume", {"role": task, "preview": result[:300]})
        return result
