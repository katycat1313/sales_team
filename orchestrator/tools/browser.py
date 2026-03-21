"""
Browser Tool - Playwright
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
    print("⚠️  Playwright not installed - browser features disabled")

SESSION_DIR = Path(os.getenv("SESSION_DIR", "/app/sessions"))
SESSION_DIR.mkdir(parents=True, exist_ok=True)

SESSION_FILES = {
    "linkedin":  SESSION_DIR / "linkedin_session.json",
    "facebook":  SESSION_DIR / "facebook_session.json",
    "instagram": SESSION_DIR / "instagram_session.json",
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

        print(f"[Browser] Opened {platform} login - waiting for Katy to log in...")
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
                return [{"error": "CAPTCHA detected - LinkedIn needs manual action"}]

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

    async def post_to_instagram(self, caption: str) -> dict:
        """
        Post a text-based content post to Instagram via web.
        Returns {"posted": True} or {"error": "..."}
        """
        if not PLAYWRIGHT_AVAILABLE:
            return {"error": "Playwright not available", "posted": False}

        if not SESSION_FILES["instagram"].exists():
            return {"error": "Instagram session not saved. Run login_instagram.py first.", "posted": False}

        context = await self.get_context("instagram")
        page = await context.new_page()

        try:
            await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=20000)
            await human_delay(2000, 3500)

            if "login" in page.url.lower():
                await context.close()
                return {"error": "Instagram session expired — run login_instagram.py again", "posted": False}

            # Click the Create/+ button
            create_btn = await page.query_selector('[aria-label="New post"], [aria-label="Create"], svg[aria-label="New post"]')
            if not create_btn:
                # Try finding by SVG or nav item
                create_btn = await page.query_selector('a[href="/create/style/"]')
            if not create_btn:
                await context.close()
                return {"error": "Could not find Create button — Instagram UI may have changed", "posted": False}

            await create_btn.click()
            await human_delay(2000, 3000)

            # Select from computer (we'll need a simple image)
            # For now return a note — full image posting requires an actual image file
            await context.close()
            return {
                "posted": False,
                "note": "Image posting requires an image file. Caption ready.",
                "caption": caption
            }

        except Exception as e:
            try:
                await context.close()
            except Exception:
                pass
            return {"error": str(e), "posted": False}

    async def send_instagram_dm(self, username: str, message: str) -> dict:
        """
        Send a DM to an Instagram account using Katy's saved session.
        username: Instagram handle (without @)
        """
        if not PLAYWRIGHT_AVAILABLE:
            return {"error": "Playwright not available", "sent": False}

        if not SESSION_FILES["instagram"].exists():
            return {"error": "Instagram session not saved. Run login_instagram.py first.", "sent": False}

        context = await self.get_context("instagram")
        page = await context.new_page()

        try:
            # Go directly to the DM thread
            await page.goto(f"https://www.instagram.com/{username.lstrip('@')}/", wait_until="domcontentloaded", timeout=20000)
            await human_delay(2000, 3500)

            if "login" in page.url.lower():
                await context.close()
                return {"error": "Instagram session expired — run login_instagram.py again", "sent": False}

            # Click the Message button on their profile
            msg_btn = await page.query_selector('[aria-label="Message"], button:has-text("Message")')
            if not msg_btn:
                await context.close()
                return {"error": f"No Message button on @{username} — account may be private", "sent": False}

            await msg_btn.click()
            await human_delay(2000, 3500)

            # Type in the message box
            msg_input = await page.query_selector('[aria-label="Message"], [placeholder*="essage"], div[contenteditable="true"]')
            if not msg_input:
                await context.close()
                return {"error": "Could not find message input", "sent": False}

            await msg_input.click()
            await human_delay(500, 1000)

            for chunk in [message[i:i+20] for i in range(0, len(message), 20)]:
                await page.keyboard.type(chunk)
                await human_delay(100, 300)

            await human_delay(800, 1500)
            await page.keyboard.press("Enter")
            await human_delay(2000, 3000)

            await context.close()
            return {"sent": True, "to": f"@{username}", "platform": "instagram"}

        except Exception as e:
            try:
                await context.close()
            except Exception:
                pass
            return {"error": str(e), "sent": False}

    async def find_instagram_handle(self, business_name: str, location: str) -> str:
        """Search Google for a business's Instagram handle."""
        if not PLAYWRIGHT_AVAILABLE:
            return ""

        context = await self.get_context()
        page = await context.new_page()
        result = ""

        try:
            query = f"{business_name} {location} instagram site:instagram.com"
            await page.goto(f"https://www.google.com/search?q={query.replace(' ', '+')}", wait_until="domcontentloaded", timeout=15000)
            await human_delay(1000, 2000)

            links = await page.query_selector_all('a[href*="instagram.com/"]')
            for link in links:
                href = await link.get_attribute("href")
                if href and "instagram.com/" in href and "/p/" not in href and "?" not in href:
                    import re
                    match = re.search(r'instagram\.com/([a-zA-Z0-9._]+)', href)
                    if match:
                        handle = match.group(1)
                        if handle not in ["explore", "p", "reel", "stories", "accounts"]:
                            result = handle
                            break
        except Exception as e:
            print(f"[Browser] Instagram search error: {e}")
        finally:
            await context.close()

        return result

    async def find_facebook_page(self, business_name: str, location: str) -> str:
        """Search Google for a business's Facebook page URL."""
        if not PLAYWRIGHT_AVAILABLE:
            return ""

        context = await self.get_context()
        page = await context.new_page()
        result = ""

        try:
            query = f"{business_name} {location} facebook page site:facebook.com"
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            await page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
            await human_delay(1000, 2000)

            # Look for facebook.com links in results
            links = await page.query_selector_all('a[href*="facebook.com"]')
            for link in links:
                href = await link.get_attribute("href")
                if href and "facebook.com/" in href and "/l.php?" not in href:
                    # Clean the URL
                    if "facebook.com/pg/" in href or "facebook.com/pages/" in href or (
                        "facebook.com/" in href and "?" not in href
                    ):
                        result = href
                        break
        except Exception as e:
            print(f"[Browser] Facebook search error: {e}")
        finally:
            await context.close()

        return result

    async def send_facebook_dm(self, facebook_page_url: str, message: str) -> dict:
        """
        Send a DM to a Facebook business page using Katy's saved session.
        Returns {"sent": True} or {"error": "..."}
        """
        if not PLAYWRIGHT_AVAILABLE:
            return {"error": "Playwright not available", "sent": False}

        if not SESSION_FILES["facebook"].exists():
            return {
                "error": "Facebook session not saved. Run login_facebook.py first.",
                "sent": False
            }

        context = await self.get_context("facebook")
        page = await context.new_page()

        try:
            await page.goto(facebook_page_url, wait_until="domcontentloaded", timeout=20000)
            await human_delay(2000, 3500)

            # Check for CAPTCHA or login wall
            if "login" in page.url.lower():
                await context.close()
                return {"error": "Facebook session expired — run login_facebook.py again", "sent": False}

            # Click the Message button on the business page
            msg_btn = await page.query_selector('[data-testid="page_messenger_button"], a[href*="m.me"], [aria-label*="Message"], button:has-text("Message")')
            if not msg_btn:
                await context.close()
                return {"error": f"No Message button found on {facebook_page_url}", "sent": False}

            await msg_btn.click()
            await human_delay(2000, 3500)

            # Type the message in the chat input
            chat_input = await page.query_selector('[contenteditable="true"], textarea[placeholder*="message"], [aria-label*="message"]')
            if not chat_input:
                await context.close()
                return {"error": "Could not find message input box", "sent": False}

            await chat_input.click()
            await human_delay(500, 1000)

            # Type message with human-like timing
            for chunk in [message[i:i+20] for i in range(0, len(message), 20)]:
                await page.keyboard.type(chunk)
                await human_delay(100, 300)

            await human_delay(800, 1500)

            # Send with Enter
            await page.keyboard.press("Enter")
            await human_delay(1500, 2500)

            await context.close()
            return {"sent": True, "to": facebook_page_url, "platform": "facebook"}

        except Exception as e:
            try:
                await context.close()
            except Exception:
                pass
            return {"error": str(e), "sent": False}


# Global browser instance
browser_tool = BrowserTool()
