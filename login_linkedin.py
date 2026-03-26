"""
Run this ONCE to save your LinkedIn session.
After this, agents can browse LinkedIn as you forever.

Usage:
  python login_linkedin.py

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

    SESSION_PATH = Path(__file__).parent / "orchestrator" / "sessions" / "linkedin_session.json"
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("\n=== LinkedIn Login ===")
    print("A browser window will open.")
    print("Log into LinkedIn normally.")
    print("The window will close automatically once you're logged in.\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=50)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.goto("https://www.linkedin.com/login")

        print("Waiting for you to log in...")

        try:
            # Wait up to 3 minutes for login to complete
            await page.wait_for_url("https://www.linkedin.com/feed/**", timeout=180000)
        except Exception:
            try:
                await page.wait_for_function(
                    "() => window.location.href.includes('linkedin.com') && !window.location.href.includes('login') && !window.location.href.includes('checkpoint')",
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

        print(f"\n✅ LinkedIn session saved to: {SESSION_PATH}")
        print("The Docker container will pick it up automatically.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
