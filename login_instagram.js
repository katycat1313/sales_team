/**
 * Run ONCE to save your Instagram session.
 * Usage: npx playwright@latest node login_instagram.js
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const SESSION_PATH = path.join(__dirname, 'orchestrator', 'sessions', 'instagram_session.json');

async function main() {
  fs.mkdirSync(path.dirname(SESSION_PATH), { recursive: true });

  console.log('\n=== Instagram Login (katycat.13) ===');
  console.log('A browser window will open.');
  console.log('Log into Instagram normally.');
  console.log('The window closes automatically once you are logged in.\n');

  const browser = await chromium.launch({ headless: false, slowMo: 50 });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
  });

  const page = await context.newPage();
  await page.goto('https://www.instagram.com/accounts/login/');

  console.log('Waiting for you to log in...');

  try {
    await page.waitForURL('https://www.instagram.com/', { timeout: 180000 });
  } catch {
    try {
      await page.waitForFunction(
        () => window.location.href === 'https://www.instagram.com/',
        { timeout: 180000 }
      );
    } catch {
      console.log('Timed out. Try running again.');
      await browser.close();
      return;
    }
  }

  const storage = await context.storageState();
  fs.writeFileSync(SESSION_PATH, JSON.stringify(storage, null, 2));
  await browser.close();

  console.log('\n✅ Instagram session saved!');
  console.log(`   Profile: katycat.13`);
  console.log(`   Location: ${SESSION_PATH}`);
  console.log('\nAgents will now warm up your page before sending DMs.\n');
}

main().catch(console.error);
