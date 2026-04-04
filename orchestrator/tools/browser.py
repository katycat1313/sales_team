"""
Browser Tool — Playwright
-------------------------
Gives agents the ability to browse the web and send messages using Katy's saved sessions.
Katy logs in once via /browser/login/{platform}, agents use the saved cookies.

Supports: LinkedIn, Facebook, Instagram, general web browsing
Safety: human-like delays, CAPTCHA detection, max actions per session
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
    "linkedin":  SESSION_DIR / "linkedin_session.json",
    "facebook":  SESSION_DIR / "facebook_session.json",
    "instagram": SESSION_DIR / "instagram_session.json",
}

LOGIN_URLS = {
    "linkedin":  "https://www.linkedin.com/login",
    "facebook":  "https://www.facebook.com/login",
    "instagram": "https://www.instagram.com/accounts/login/",
}

POST_LOGIN_URLS = {
    "linkedin":  "https://www.linkedin.com/feed/",
    "facebook":  "https://www.facebook.com/",
    "instagram": "https://www.instagram.com/",
}


async def human_delay(min_ms: int = 800, max_ms: int = 2400):
    """Random human-like pause between actions."""
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


async def human_type(page, selector: str, text: str):
    """Type text character by character like a human."""
    await page.click(selector)
    for char in text:
        await page.keyboard.type(char)
        await asyncio.sleep(random.uniform(0.04, 0.14))


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
        """Get a browser context, loaded with saved session if available."""
        storage_state = None
        if platform and SESSION_FILES.get(platform, Path("")).exists():
            with open(SESSION_FILES[platform]) as f:
                storage_state = json.load(f)
            print(f"[Browser] Loaded {platform} session")

        context = await self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            storage_state=storage_state,
        )
        return context

    async def save_session(self, context: BrowserContext, platform: str):
        """Persist cookies/storage after login so agents reuse them."""
        storage = await context.storage_state()
        with open(SESSION_FILES[platform], "w") as f:
            json.dump(storage, f)
        print(f"[Browser] Saved {platform} session")

    # ── Login ─────────────────────────────────────────────────────────────────

    async def login_flow(self, platform: str) -> str:
        """
        Opens a visible browser for Katy to log in manually.
        Saves the session when done so agents can use it forever.
        """
        if not PLAYWRIGHT_AVAILABLE:
            return "Playwright not installed"

        if platform not in LOGIN_URLS:
            return f"Unknown platform: {platform}. Supported: {list(LOGIN_URLS.keys())}"

        visible_browser = await self.playwright.chromium.launch(headless=False)
        context = await visible_browser.new_context()
        page = await context.new_page()
        await page.goto(LOGIN_URLS[platform])

        print(f"[Browser] Opened {platform} login — waiting for Katy to log in...")

        try:
            await page.wait_for_url(f"{POST_LOGIN_URLS[platform]}**", timeout=120000)
            await human_delay(1500, 2500)
            await self.save_session(context, platform)
            await visible_browser.close()
            return f"✅ {platform.title()} session saved! Agents can now send messages as Katy on {platform.title()}."
        except Exception as e:
            await visible_browser.close()
            return f"❌ Login timeout or error: {e}"

    # ── LinkedIn ──────────────────────────────────────────────────────────────

    async def linkedin_search_businesses(self, niche: str, location: str = "") -> list:
        """
        Search LinkedIn for service business owners and decision-makers.
        Returns profiles that could be pitched for Missed-Call-Revenue.
        """
        if not PLAYWRIGHT_AVAILABLE or not SESSION_FILES["linkedin"].exists():
            return [{"error": "LinkedIn session not set up. Run /browser/login/linkedin first."}]

        results = []
        context = await self.get_context("linkedin")
        page = await context.new_page()

        try:
            loc_query = f"&geoUrn=%22{location}%22" if location else ""
            search_url = (
                f"https://www.linkedin.com/search/results/people/"
                f"?keywords={niche.replace(' ', '%20')}%20owner%20OR%20founder%20OR%20operator"
                f"{loc_query}&origin=GLOBAL_SEARCH_HEADER"
            )
            await page.goto(search_url)
            await human_delay(2000, 4000)

            if await page.query_selector(".captcha-challenge, #challenge-form"):
                await context.close()
                return [{"error": "CAPTCHA — LinkedIn session may need refresh. Run /browser/login/linkedin."}]

            people = await page.query_selector_all(".reusable-search__result-container")
            for person in people[:8]:
                try:
                    name_el    = await person.query_selector(".actor-name, .entity-result__title-text a span[aria-hidden='true']")
                    title_el   = await person.query_selector(".subline-level-1, .entity-result__primary-subtitle")
                    company_el = await person.query_selector(".subline-level-2, .entity-result__secondary-subtitle")
                    link_el    = await person.query_selector("a.app-aware-link")
                    results.append({
                        "name":    await name_el.inner_text()    if name_el    else "",
                        "title":   await title_el.inner_text()   if title_el   else "",
                        "company": await company_el.inner_text() if company_el else "",
                        "url":     await link_el.get_attribute("href") if link_el else "",
                        "source":  "linkedin",
                    })
                    await human_delay(300, 700)
                except Exception:
                    continue
        except Exception as e:
            results = [{"error": str(e)}]
        finally:
            await context.close()

        return results

    async def linkedin_send_dm(self, profile_url: str, message: str) -> dict:
        """
        Send a LinkedIn direct message to a profile URL as Katy.
        Opens the profile, clicks Message, types the message, sends it.
        Returns {"sent": bool, "error": str?}
        """
        if not PLAYWRIGHT_AVAILABLE or not SESSION_FILES["linkedin"].exists():
            return {"sent": False, "error": "LinkedIn session not set up. Run /browser/login/linkedin first."}

        context = await self.get_context("linkedin")
        page = await context.new_page()

        try:
            await page.goto(profile_url, wait_until="domcontentloaded")
            await human_delay(2000, 3500)

            # Check CAPTCHA
            if await page.query_selector(".captcha-challenge, #challenge-form"):
                await context.close()
                return {"sent": False, "error": "CAPTCHA detected — LinkedIn session needs refresh."}

            # Click the Message button on the profile
            msg_button = await page.query_selector(
                "button.pvs-profile-actions__action[aria-label*='Message'], "
                "button[aria-label*='Message'], "
                "a[data-control-name='send_inmail']"
            )
            if not msg_button:
                await context.close()
                return {"sent": False, "error": "Message button not found — profile may not be a connection or button changed."}

            await msg_button.click()
            await human_delay(1500, 2500)

            # Type message in the compose box
            compose = await page.query_selector(
                ".msg-form__contenteditable, "
                "div[contenteditable='true'][role='textbox']"
            )
            if not compose:
                await context.close()
                return {"sent": False, "error": "Message compose box not found."}

            await compose.click()
            await human_delay(400, 800)

            # Type human-like
            for char in message:
                await page.keyboard.type(char)
                await asyncio.sleep(random.uniform(0.03, 0.12))

            await human_delay(800, 1500)

            # Send
            send_btn = await page.query_selector(
                "button.msg-form__send-button[type='submit'], "
                "button[aria-label='Send'], "
                "button.send-button"
            )
            if not send_btn:
                await context.close()
                return {"sent": False, "error": "Send button not found."}

            await send_btn.click()
            await human_delay(1000, 2000)

            return {"sent": True}
        except Exception as e:
            return {"sent": False, "error": str(e)}
        finally:
            await context.close()

    # ── Facebook ──────────────────────────────────────────────────────────────

    async def facebook_send_message(self, profile_url: str, message: str) -> dict:
        """
        Send a Facebook Messenger message to a profile or page URL as Katy.
        Returns {"sent": bool, "error": str?}
        """
        if not PLAYWRIGHT_AVAILABLE or not SESSION_FILES["facebook"].exists():
            return {"sent": False, "error": "Facebook session not set up. Run /browser/login/facebook first."}

        context = await self.get_context("facebook")
        page = await context.new_page()

        try:
            await page.goto(profile_url, wait_until="domcontentloaded")
            await human_delay(2000, 3500)

            # Facebook Business Pages have a "Send Message" button
            msg_button = await page.query_selector(
                "a[href*='/messages/'], "
                "div[aria-label='Send message'], "
                "a[data-testid='send-message-button']"
            )
            if not msg_button:
                await context.close()
                return {"sent": False, "error": "Message button not found on this profile/page."}

            await msg_button.click()
            await human_delay(2000, 3500)

            # Messenger input box
            compose = await page.query_selector(
                "div[contenteditable='true'][role='textbox'], "
                "div[aria-label='Message'], "
                "div[data-lexical-editor='true']"
            )
            if not compose:
                await context.close()
                return {"sent": False, "error": "Message input not found."}

            await compose.click()
            await human_delay(400, 900)

            for char in message:
                await page.keyboard.type(char)
                await asyncio.sleep(random.uniform(0.04, 0.13))

            await human_delay(800, 1600)

            # Send with Enter
            await page.keyboard.press("Enter")
            await human_delay(1000, 2000)

            return {"sent": True}
        except Exception as e:
            return {"sent": False, "error": str(e)}
        finally:
            await context.close()

    async def facebook_search_businesses(self, niche: str, location: str = "") -> list:
        """Search Facebook for local service businesses."""
        if not PLAYWRIGHT_AVAILABLE or not SESSION_FILES["facebook"].exists():
            return [{"error": "Facebook session not set up. Run /browser/login/facebook first."}]

        results = []
        context = await self.get_context("facebook")
        page = await context.new_page()

        try:
            query = f"{niche} {location}".strip().replace(" ", "%20")
            await page.goto(f"https://www.facebook.com/search/pages/?q={query}")
            await human_delay(2500, 4000)

            page_cards = await page.query_selector_all("[data-testid='browse-search-result-card'], div[role='article']")
            for card in page_cards[:8]:
                try:
                    name_el = await card.query_selector("span[dir='auto'], strong")
                    link_el = await card.query_selector("a[href*='facebook.com']")
                    results.append({
                        "name":   await name_el.inner_text() if name_el else "",
                        "url":    await link_el.get_attribute("href") if link_el else "",
                        "source": "facebook",
                    })
                    await human_delay(200, 500)
                except Exception:
                    continue
        except Exception as e:
            results = [{"error": str(e)}]
        finally:
            await context.close()

        return results

    # ── Instagram ─────────────────────────────────────────────────────────────

    async def instagram_send_dm(self, username: str, message: str) -> dict:
        """
        Send an Instagram DM to a username as Katy.
        Returns {"sent": bool, "error": str?}
        """
        if not PLAYWRIGHT_AVAILABLE or not SESSION_FILES["instagram"].exists():
            return {"sent": False, "error": "Instagram session not set up. Run /browser/login/instagram first."}

        context = await self.get_context("instagram")
        page = await context.new_page()

        try:
            # Go directly to the DM compose URL
            await page.goto(f"https://www.instagram.com/direct/new/", wait_until="domcontentloaded")
            await human_delay(2000, 3500)

            # Search for username in the recipient box
            recipient_input = await page.query_selector("input[placeholder*='Search'], input[name='queryBox']")
            if not recipient_input:
                await context.close()
                return {"sent": False, "error": "DM recipient search box not found — Instagram UI may have changed."}

            await recipient_input.click()
            await human_delay(500, 900)
            for char in username:
                await page.keyboard.type(char)
                await asyncio.sleep(random.uniform(0.06, 0.14))
            await human_delay(1500, 2500)

            # Click matching result
            result = await page.query_selector(f"div[role='button']:has-text('{username}'), span:has-text('{username}')")
            if result:
                await result.click()
                await human_delay(800, 1500)
            else:
                await context.close()
                return {"sent": False, "error": f"User @{username} not found in search results."}

            # Confirm recipient and open chat
            next_btn = await page.query_selector("button:has-text('Next'), div[role='button']:has-text('Next')")
            if next_btn:
                await next_btn.click()
                await human_delay(1500, 2500)

            # Type message
            compose = await page.query_selector(
                "textarea[placeholder*='Message'], "
                "div[contenteditable='true'][role='textbox'], "
                "div[aria-label*='Message']"
            )
            if not compose:
                await context.close()
                return {"sent": False, "error": "Message input box not found."}

            await compose.click()
            await human_delay(400, 800)
            for char in message:
                await page.keyboard.type(char)
                await asyncio.sleep(random.uniform(0.04, 0.12))

            await human_delay(800, 1500)
            await page.keyboard.press("Enter")
            await human_delay(1200, 2000)

            return {"sent": True}
        except Exception as e:
            return {"sent": False, "error": str(e)}
        finally:
            await context.close()

    # ── General ───────────────────────────────────────────────────────────────

    async def general_browse(self, url: str, extract: str = "text") -> str:
        """Browse any URL and extract content."""
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
