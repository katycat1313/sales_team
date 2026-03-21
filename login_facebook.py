"""
Run this ONCE to save your Facebook session.
After this, agents can send DMs as you forever.

Usage:
  python login_facebook.py

Requirements:
  pip install playwright
  playwright install chromium
"""
import asyncio
import json
from pathlib import Path

async def main():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Installing playwright...")
        import subprocess
        subprocess.run(["pip", "install", "playwright"], check=True)
        subprocess.run(["playwright", "install", "chromium"], check=True)
        from playwright.async_api import async_playwright

    SESSION_PATH = Path(__file__).parent / "orchestrator" / "sessions" / "facebook_session.json"
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("\n=== Facebook Login ===")
    print("A browser window will open.")
    print("Log into Facebook normally.")
    print("The window will close automatically once you're logged in.\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=50)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.goto("https://www.facebook.com/login")

        print("Waiting for you to log in...")

        try:
            # Wait up to 3 minutes for login to complete
            await page.wait_for_url("https://www.facebook.com/", timeout=180000)
        except Exception:
            try:
                # Sometimes lands on a different URL after login
                await page.wait_for_function(
                    "() => window.location.href.includes('facebook.com') && !window.location.href.includes('login')",
                    timeout=180000
                )
            except Exception:
                print("Timeout — did you log in? Try running again.")
                await browser.close()
                return

        # Save session
        storage = await context.storage_state()
        with open(SESSION_PATH, "w") as f:
            json.dump(storage, f)

        await browser.close()

    print(f"\n✅ Facebook session saved!")
    print(f"   Location: {SESSION_PATH}")
    print(f"\nAgents can now send Facebook DMs as you.")
    print("You never need to do this again unless you log out of Facebook.\n")

if __name__ == "__main__":
    asyncio.run(main())
