"""
Review Miner
------------
Finds local service businesses where customers are publicly complaining about
unanswered calls, long wait times, and voicemail.

These are the highest-intent prospects for Missed-Call-Revenue — their customers
are already documenting the exact problem we solve, in public, right now.

Sources:
- Yelp (via review-text search — no Playwright needed)
- Google Maps reviews (via Playwright)
"""

import asyncio
import json
import re
import random
import httpx
from typing import Optional

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Keywords that signal missed-call / response pain in reviews
CALL_COMPLAINT_KEYWORDS = [
    "no one answered", "didn't answer", "does not answer", "never answers",
    "couldn't reach", "can't reach", "hard to reach",
    "went to voicemail", "goes to voicemail", "straight to voicemail", "got voicemail",
    "left a message", "left messages", "no callback", "never called back",
    "didn't call back", "doesn't call back", "call back",
    "long wait", "long hold", "put on hold", "on hold forever", "waited on hold",
    "took forever", "took days", "took a week", "waited all day",
    "not responsive", "unresponsive", "slow to respond", "slow response",
    "never picked up", "won't pick up", "doesn't pick up",
    "after hours", "emergency", "couldn't get through",
    "busy signal", "disconnected", "hung up",
    "no response", "ignored my calls", "ignores calls",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
]

def _rand_ua(): return random.choice(USER_AGENTS)
def _headers(): return {"User-Agent": _rand_ua(), "Accept-Language": "en-US,en;q=0.9"}
async def _delay(lo=600, hi=1800): await asyncio.sleep(random.uniform(lo/1000, hi/1000))


def score_complaint_text(text: str) -> tuple[int, list[str]]:
    """
    Score a block of review text for call complaint keywords.
    Returns (score 0-10, list of matched phrases).
    """
    text_lower = text.lower()
    matches = [kw for kw in CALL_COMPLAINT_KEYWORDS if kw in text_lower]
    score = min(10, len(matches) * 3)
    return score, matches


# ── Yelp review-text search ───────────────────────────────────────────────────

async def search_yelp_complaints(niche: str, location: str, limit: int = 15) -> list:
    """
    Search Yelp for businesses where review text contains call complaint keywords.
    Yelp's search supports full-text search within reviews via the find_desc parameter.
    Returns list of {name, url, phone, address, complaint_reviews, complaint_score, priority}.
    """
    complaint_phrases = [
        "voicemail no answer",
        "couldn't reach no answer",
        "no callback long wait",
        "no answer unanswered",
    ]

    found_businesses: dict[str, dict] = {}

    for phrase in complaint_phrases:
        if len(found_businesses) >= limit:
            break

        niche_q  = niche.replace(" ", "+")
        phrase_q = phrase.replace(" ", "+")
        loc_q    = location.replace(" ", "+")
        url = (
            f"https://www.yelp.com/search"
            f"?find_desc={niche_q}+%22{phrase_q}%22"
            f"&find_loc={loc_q}"
        )

        try:
            async with httpx.AsyncClient(
                headers=_headers(), follow_redirects=True, timeout=20
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue
                html = resp.text
        except Exception as e:
            print(f"[ReviewMiner] Yelp request failed for '{phrase}': {e}")
            continue

        await _delay(800, 1500)

        # Extract business cards from JSON-LD
        json_ld_blocks = re.findall(
            r'<script type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.DOTALL
        )
        for block in json_ld_blocks:
            try:
                data = json.loads(block)
                items = data if isinstance(data, list) else data.get("itemListElement", [])
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    biz = item.get("item", item)
                    name = (biz.get("name") or "").strip()
                    if not name or name in found_businesses:
                        continue
                    addr  = biz.get("address") or {}
                    phone = biz.get("telephone", "")
                    biz_url = biz.get("url", "")
                    rating  = str((biz.get("aggregateRating") or {}).get("ratingValue", ""))
                    found_businesses[name] = {
                        "name": name,
                        "phone": phone,
                        "address": (
                            addr.get("streetAddress", "") + " " +
                            addr.get("addressLocality", "")
                        ).strip() or location,
                        "yelp_url": biz_url,
                        "rating": rating,
                        "complaint_phrase": phrase,
                        "source": "yelp",
                        "location": location,
                        "niche": niche,
                    }
                    if len(found_businesses) >= limit:
                        break
            except Exception:
                continue

        # Fallback: extract /biz/ links when JSON-LD yields nothing
        if not found_businesses:
            biz_slugs = re.findall(r'href="/biz/([^"?]+)"', html)
            seen_slugs = set()
            for slug in biz_slugs[:limit]:
                if slug in seen_slugs:
                    continue
                seen_slugs.add(slug)
                # Convert slug to readable name
                readable = slug.split("?")[0].replace("-", " ").title()
                if readable not in found_businesses:
                    found_businesses[readable] = {
                        "name": readable,
                        "phone": "",
                        "address": location,
                        "yelp_url": f"https://www.yelp.com/biz/{slug}",
                        "complaint_phrase": phrase,
                        "source": "yelp",
                        "location": location,
                        "niche": niche,
                    }

    results = []
    for biz in list(found_businesses.values())[:limit]:
        # Fetch review snippets to extract actual complaint text
        complaint_snippets = await _fetch_yelp_review_snippets(biz.get("yelp_url", ""))
        score, matched = score_complaint_text(" ".join(complaint_snippets))
        biz["complaint_reviews"] = complaint_snippets[:3]
        biz["complaint_keywords"] = matched
        biz["complaint_score"]   = score
        biz["priority"] = "HOT" if score >= 3 else "WARM"
        results.append(biz)

    print(f"[ReviewMiner] Yelp complaints: {len(results)} businesses found for '{niche}' in '{location}'")
    return results


async def _fetch_yelp_review_snippets(yelp_url: str, limit: int = 5) -> list[str]:
    """Fetch the first page of reviews for a Yelp business and return snippet texts."""
    if not yelp_url:
        return []
    try:
        async with httpx.AsyncClient(
            headers=_headers(), follow_redirects=True, timeout=15
        ) as client:
            resp = await client.get(yelp_url)
            if resp.status_code != 200:
                return []
            html = resp.text
    except Exception:
        return []

    # Review text lives in <p class="..."> inside review containers, or in JSON
    snippets = []

    # Try to extract from JSON-LD Review items
    json_ld_blocks = re.findall(
        r'<script type="application/ld\+json"[^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    for block in json_ld_blocks:
        try:
            data = json.loads(block)
            reviews = data.get("review", [])
            for rev in reviews:
                body = (rev.get("reviewBody") or "").strip()
                if body:
                    snippets.append(body[:400])
                if len(snippets) >= limit:
                    break
        except Exception:
            continue
        if len(snippets) >= limit:
            break

    # Fallback: extract text from <p> tags that look like review bodies
    if not snippets:
        p_texts = re.findall(r'<p[^>]*class="[^"]*comment[^"]*"[^>]*>(.*?)</p>', html, re.DOTALL)
        for text in p_texts[:limit]:
            clean = re.sub(r'<[^>]+>', '', text).strip()
            if len(clean) > 30:
                snippets.append(clean[:400])

    return snippets[:limit]


# ── Google Maps review mining (Playwright) ────────────────────────────────────

async def mine_google_maps_reviews(maps_url: str, business_name: str = "") -> dict:
    """
    Visit a Google Maps business page, navigate to Reviews tab,
    scroll to load reviews, extract text, and score for call complaints.
    Returns {complaint_score, complaint_keywords, review_snippets, has_call_complaints}.
    """
    if not PLAYWRIGHT_AVAILABLE or not maps_url:
        return {"complaint_score": 0, "complaint_keywords": [], "review_snippets": [], "has_call_complaints": False}

    review_texts = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=_rand_ua(),
            locale="en-US",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = await context.new_page()

        try:
            await page.goto(maps_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # Handle consent
            for sel in ['button[aria-label*="Accept all"]', '#L2AGLb', '#W0wltc']:
                try:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(1.5)
                        break
                except Exception:
                    pass

            # Click the Reviews tab
            reviews_tab = await page.query_selector(
                'button[aria-label*="Reviews"], '
                '[data-tab-index="1"], '
                'button:has-text("Reviews")'
            )
            if reviews_tab:
                await reviews_tab.click()
                await asyncio.sleep(2)

            # Scroll to load more reviews
            for _ in range(5):
                await page.evaluate("""() => {
                    const feed = document.querySelector('[role="feed"]');
                    if (feed) feed.scrollTop += 1000;
                    else window.scrollBy(0, 800);
                }""")
                await asyncio.sleep(1.2)

            # Expand "More" buttons to get full review text
            more_buttons = await page.query_selector_all('button[aria-label*="See more"], button.w8nwRe')
            for btn in more_buttons[:10]:
                try:
                    await btn.click()
                    await asyncio.sleep(0.3)
                except Exception:
                    pass

            # Extract review text
            review_texts = await page.evaluate("""() => {
                const texts = [];
                // Google Maps review text containers (class changes but role is consistent)
                const selectors = [
                    '[data-review-id] [data-text="true"]',
                    '[jsan*="review"] .wiI7pd',
                    '.MyEned span[jsname]',
                    '[class*="review"] span',
                ];
                for (const sel of selectors) {
                    document.querySelectorAll(sel).forEach(el => {
                        const t = el.textContent.trim();
                        if (t.length > 30 && !texts.includes(t)) {
                            texts.push(t.substring(0, 400));
                        }
                    });
                    if (texts.length >= 15) break;
                }
                return texts.slice(0, 15);
            }""")

        except Exception as e:
            print(f"[ReviewMiner] Google Maps review mining failed for {business_name}: {e}")
        finally:
            await browser.close()

    if not review_texts:
        return {"complaint_score": 0, "complaint_keywords": [], "review_snippets": [], "has_call_complaints": False}

    full_text = " ".join(review_texts)
    score, matched = score_complaint_text(full_text)

    # Find the specific complaint snippets
    complaint_snippets = [
        rev for rev in review_texts
        if any(kw in rev.lower() for kw in CALL_COMPLAINT_KEYWORDS)
    ]

    return {
        "complaint_score": score,
        "complaint_keywords": matched,
        "review_snippets": complaint_snippets[:3],
        "has_call_complaints": score > 0,
    }


# ── Main scan: find businesses with call complaints ───────────────────────────

async def scan_for_call_complaints(niche: str, location: str, limit: int = 15) -> list:
    """
    Full pipeline: find service businesses in a niche + location where
    customers have complained about unanswered calls or slow response.

    Returns a list sorted by complaint_score (highest first).
    These are the hottest prospects for Missed-Call-Revenue.
    """
    print(f"\n[ReviewMiner] ═══ COMPLAINT SCAN: {niche} in {location} ═══")

    # 1. Get businesses from Yelp complaint search (fast, no Playwright)
    yelp_results = await search_yelp_complaints(niche, location, limit=limit)

    # 2. Also get businesses from regular scan and check their Maps reviews
    #    (only for top businesses to keep runtime reasonable)
    maps_enriched = []
    if PLAYWRIGHT_AVAILABLE and len(yelp_results) < 5:
        try:
            from tools.gbp_audit import search_google_maps
            raw_businesses = await search_google_maps(niche, location, limit=8)
            valid = [b for b in raw_businesses if "error" not in b and b.get("maps_url")]
            for biz in valid[:4]:  # Limit Playwright calls
                maps_url = biz.get("maps_url", "")
                if not maps_url:
                    continue
                complaint_data = await mine_google_maps_reviews(maps_url, biz.get("name", ""))
                if complaint_data.get("has_call_complaints"):
                    biz.update(complaint_data)
                    biz["source"] = "google_maps_reviews"
                    biz["priority"] = "HOT"
                    maps_enriched.append(biz)
                await _delay(1000, 2000)
        except Exception as e:
            print(f"[ReviewMiner] Maps review scan failed: {e}")

    # Merge and deduplicate
    all_results = yelp_results + maps_enriched
    seen_names: set[str] = set()
    deduped = []
    for biz in all_results:
        name = biz.get("name", "").lower().strip()
        if name and name not in seen_names:
            seen_names.add(name)
            deduped.append(biz)

    # Sort by complaint score descending
    deduped.sort(key=lambda x: x.get("complaint_score", 0), reverse=True)

    print(f"[ReviewMiner] Found {len(deduped)} businesses with call complaints")
    return deduped[:limit]
