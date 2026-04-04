"""
Browser Tool — Playwright
-------------------------
Gives agents the ability to browse the web using your saved sessions.
You log in once, agents use your cookies forever.

Supports: LinkedIn, Facebook, general web browsing
Safety: human-like delays, max actions per session, stops on CAPTCHA
"""

import asyncio
import json
import os
import random
from pathlib import Path
from typing import Optional

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("⚠️  Playwright not installed — browser features disabled")

SESSION_DIR = Path(os.getenv("SESSION_DIR", "/app/sessions"))
SESSION_DIR.mkdir(parents=True, exist_ok=True)

SESSION_FILES = {
    "linkedin": SESSION_DIR / "linkedin_session.json",
    "facebook": SESSION_DIR / "facebook_session.json",
}

async def human_delay(min_ms: int = 800, max_ms: int = 2400):
    """Random human-like delay between actions"""
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

class BrowserTool:
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None

    async def start(self):
        if not PLAYWRIGHT_AVAILABLE:
            return False
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        return True

    async def stop(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def get_context(self, platform: str = None) -> BrowserContext:
        """Get a browser context, loaded with saved session if available"""
        storage_state = None
        if platform and SESSION_FILES.get(platform, Path("")).exists():
            with open(SESSION_FILES[platform]) as f:
                storage_state = json.load(f)
            print(f"[Browser] Loaded {platform} session")

        context = await self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            storage_state=storage_state
        )
        return context

    async def save_session(self, context: BrowserContext, platform: str):
        """Save session cookies after login"""
        storage = await context.storage_state()
        with open(SESSION_FILES[platform], "w") as f:
            json.dump(storage, f)
        print(f"[Browser] Saved {platform} session")

    async def login_flow(self, platform: str) -> str:
        """
        Opens a visible browser for Katy to log in manually.
        Saves the session when done.
        Returns instructions for Katy.
        """
        if not PLAYWRIGHT_AVAILABLE:
            return "Playwright not installed"

        urls = {
            "linkedin": "https://www.linkedin.com/login",
            "facebook": "https://www.facebook.com/login",
        }

        if platform not in urls:
            return f"Unknown platform: {platform}"

        # Launch visible browser for manual login
        visible_browser = await self.playwright.chromium.launch(headless=False)
        context = await visible_browser.new_context()
        page = await context.new_page()
        await page.goto(urls[platform])

        print(f"[Browser] Opened {platform} login — waiting for Katy to log in...")
        print(f"[Browser] Will save session automatically when login is detected")

        # Wait for login to complete (URL changes away from login page)
        try:
            if platform == "linkedin":
                await page.wait_for_url("https://www.linkedin.com/feed/**", timeout=120000)
            elif platform == "facebook":
                await page.wait_for_url("https://www.facebook.com/", timeout=120000)

            await self.save_session(context, platform)
            await visible_browser.close()
            return f"✅ {platform.title()} session saved! Agents can now browse {platform.title()}."
        except Exception as e:
            await visible_browser.close()
            return f"❌ Login timeout or error: {e}"

    async def linkedin_search_jobs(self, keywords: str, location: str = "Remote") -> list:
        """Search LinkedIn jobs and return results"""
        if not PLAYWRIGHT_AVAILABLE or not SESSION_FILES["linkedin"].exists():
            return [{"error": "LinkedIn session not set up. Run /login linkedin first."}]

        results = []
        context = await self.get_context("linkedin")
        page = await context.new_page()

        try:
            search_url = f"https://www.linkedin.com/jobs/search/?keywords={keywords.replace(' ', '%20')}&location={location}&f_WT=2"
            await page.goto(search_url)
            await human_delay(2000, 4000)

            # Check for CAPTCHA
            if await page.query_selector(".captcha-challenge"):
                await context.close()
                return [{"error": "CAPTCHA detected — LinkedIn needs manual action"}]

            # Extract job listings
            job_cards = await page.query_selector_all(".job-card-container")
            for card in job_cards[:10]:
                try:
                    title = await card.query_selector(".job-card-list__title")
                    company = await card.query_selector(".job-card-container__company-name")
                    location_el = await card.query_selector(".job-card-container__metadata-item")
                    link = await card.query_selector("a.job-card-container__link")

                    results.append({
                        "title": await title.inner_text() if title else "",
                        "company": await company.inner_text() if company else "",
                        "location": await location_el.inner_text() if location_el else "",
                        "url": await link.get_attribute("href") if link else "",
                        "source": "linkedin"
                    })
                    await human_delay(200, 600)
                except:
                    continue
        except Exception as e:
            results = [{"error": str(e)}]
        finally:
            await context.close()

        return results

    async def linkedin_find_recruiter(self, company: str) -> list:
        """Find recruiters at a specific company on LinkedIn"""
        if not PLAYWRIGHT_AVAILABLE or not SESSION_FILES["linkedin"].exists():
            return [{"error": "LinkedIn session not set up"}]

        results = []
        context = await self.get_context("linkedin")
        page = await context.new_page()

        try:
            search_url = f"https://www.linkedin.com/search/results/people/?keywords=recruiter%20{company.replace(' ', '%20')}&origin=GLOBAL_SEARCH_HEADER"
            await page.goto(search_url)
            await human_delay(2000, 3500)

            people = await page.query_selector_all(".reusable-search__result-container")
            for person in people[:5]:
                try:
                    name = await person.query_selector(".actor-name")
                    title = await person.query_selector(".subline-level-1")
                    link = await person.query_selector("a.app-aware-link")
                    results.append({
                        "name": await name.inner_text() if name else "",
                        "title": await title.inner_text() if title else "",
                        "url": await link.get_attribute("href") if link else "",
                        "company": company,
                        "source": "linkedin"
                    })
                    await human_delay(300, 800)
                except:
                    continue
        except Exception as e:
            results = [{"error": str(e)}]
        finally:
            await context.close()

        return results

    async def general_browse(self, url: str, extract: str = "text") -> str:
        """Browse any URL and extract content"""
        if not PLAYWRIGHT_AVAILABLE:
            return "Playwright not available"

        context = await self.get_context()
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded")
            await human_delay(1000, 2000)

            if extract == "text":
                content = await page.inner_text("body")
                return content[:5000]
            elif extract == "title":
                return await page.title()
            else:
                return await page.content()
        except Exception as e:
            return f"Error browsing {url}: {e}"
        finally:
            await context.close()

# Global browser instance
browser_tool = BrowserTool()
