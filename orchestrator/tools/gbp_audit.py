"""
GBP Audit Tool v2
-----------------
Multi-source business discovery + GBP completeness scoring.

Why this beats the old version:
- Yellow Pages = simple HTML, no bot detection, phone numbers built-in
- Google Maps = improved Playwright with JS extraction (no fragile CSS classes)
- GBP Check = fast httpx Google search (no full Playwright page load per business)

Sources tried in order:
1. Yellow Pages  (primary — reliable, has phones)
2. Yelp HTML     (secondary — more dynamic businesses)
3. Google Maps   (fallback — Playwright with consent handling)
"""

import asyncio
import json
import random
import re
import httpx
from typing import Optional

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Rotate user agents to avoid blocks
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

def _rand_ua():
    return random.choice(USER_AGENTS)

def _http_headers():
    return {
        "User-Agent": _rand_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

async def _human_delay(min_ms=600, max_ms=2000):
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


# ─── SOURCE 1: Yellow Pages ────────────────────────────────────────────────────

async def search_yellowpages(niche: str, location: str, limit: int = 20) -> list:
    """
    Scrape Yellow Pages — most reliable source for US local businesses.
    Returns name, phone, address, website, category.
    Phone numbers are displayed right on the search page.
    """
    niche_q   = niche.replace(" ", "+").replace("&", "%26")
    loc_q     = location.replace(" ", "+").replace(",", "%2C")
    url = f"https://www.yellowpages.com/search?search_terms={niche_q}&geo_location_terms={loc_q}"

    try:
        async with httpx.AsyncClient(
            headers=_http_headers(), follow_redirects=True, timeout=25
        ) as client:
            resp = await client.get(url)
            html = resp.text
    except Exception as e:
        return [{"error": f"YellowPages request failed: {e}"}]

    if resp.status_code != 200 or len(html) < 2000:
        return [{"error": f"YellowPages returned {resp.status_code}"}]

    businesses = []
    seen_names = set()

    # YP wraps each listing in a <div class="result"> or <div class="organic">
    # Split on these divs to isolate each business block
    blocks = re.split(r'(?=<div[^>]+class="[^"]*(?:result|organic)[^"]*")', html)

    for block in blocks[1:limit + 5]:
        if len(businesses) >= limit:
            break
        try:
            # Business name — appears in <a class="business-name">
            name_m = re.search(r'class="business-name"[^>]*>([^<]+)</a>', block)
            if not name_m:
                # Try alternate selector
                name_m = re.search(r'<a[^>]+class="[^"]*n[^"]*"[^>]*>\s*<span[^>]*>([^<]+)</span>', block)
            if not name_m:
                continue
            name = re.sub(r'\s+', ' ', name_m.group(1)).strip()
            if not name or len(name) < 2 or name in seen_names:
                continue
            seen_names.add(name)

            # Phone — <div class="phones phone primary">
            phone_m = re.search(r'class="phones phone primary">([^<]+)</div>', block)
            phone = phone_m.group(1).strip() if phone_m else ""

            # Street address
            street_m = re.search(r'class="street-address">([^<]+)</span>', block)
            city_m   = re.search(r'class="locality">([^<]+)</span>', block)
            addr_parts = []
            if street_m: addr_parts.append(street_m.group(1).strip())
            if city_m:   addr_parts.append(city_m.group(1).strip())
            address = ", ".join(addr_parts) if addr_parts else location

            # Website
            web_m = re.search(r'class="track-visit-website"[^>]*href="([^"]+)"', block)
            # Also try: <a ... rel="nofollow" ... href="http...">
            if not web_m:
                web_m = re.search(r'href="(https?://(?!www\.yellowpages)[^"]+)"[^>]*class="[^"]*website[^"]*"', block)
            website = web_m.group(1).strip() if web_m else ""

            # Category
            cat_m = re.search(r'class="categories"[^>]*>.*?<a[^>]*>([^<]+)</a>', block, re.DOTALL)
            category = cat_m.group(1).strip() if cat_m else niche

            # Rating
            rating_m = re.search(r'"ratingValue"[^>]*>([^<]+)<', block)
            if not rating_m:
                rating_m = re.search(r'(\d+\.?\d*)\s*out of\s*5', block)
            rating = rating_m.group(1).strip() if rating_m else ""

            # Review count
            rev_m = re.search(r'(\d+)\s*(?:Reviews?|reviews?)', block)
            review_count = rev_m.group(1) if rev_m else ""

            businesses.append({
                "name": name,
                "phone": phone,
                "address": address,
                "website": website,
                "category": category,
                "rating": rating,
                "review_count": review_count,
                "location": location,
                "niche": niche,
                "source": "yellowpages",
            })

        except Exception:
            continue

    print(f"[YP] Found {len(businesses)} businesses for '{niche}' in '{location}'")
    return businesses


# ─── SOURCE 2: Yelp ────────────────────────────────────────────────────────────

async def search_yelp(niche: str, location: str, limit: int = 20) -> list:
    """
    Scrape Yelp search results for local businesses.
    Extracts name, address, phone (when visible), category, rating.
    """
    niche_q = niche.replace(" ", "+")
    loc_q   = location.replace(" ", "+")
    url = f"https://www.yelp.com/search?find_desc={niche_q}&find_loc={loc_q}"

    headers = _http_headers()
    headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

    try:
        async with httpx.AsyncClient(
            headers=headers, follow_redirects=True, timeout=25
        ) as client:
            resp = await client.get(url)
            html = resp.text
    except Exception as e:
        return [{"error": f"Yelp request failed: {e}"}]

    if resp.status_code != 200 or len(html) < 2000:
        return [{"error": f"Yelp returned {resp.status_code}"}]

    businesses = []
    seen_names = set()

    # Yelp embeds data in JSON-LD blocks and inline JSON state
    # Try to extract from <script type="application/ld+json"> blocks first
    json_ld_blocks = re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
    for block in json_ld_blocks:
        try:
            data = json.loads(block)
            items = data if isinstance(data, list) else data.get("itemListElement", [])
            for item in items:
                if isinstance(item, dict):
                    biz = item.get("item", item)
                    name = biz.get("name", "")
                    if not name or name in seen_names:
                        continue
                    seen_names.add(name)
                    addr = biz.get("address", {})
                    businesses.append({
                        "name": name,
                        "phone": biz.get("telephone", ""),
                        "address": addr.get("streetAddress", "") + ", " + addr.get("addressLocality", "") if addr else location,
                        "website": biz.get("url", ""),
                        "rating": str(biz.get("aggregateRating", {}).get("ratingValue", "")),
                        "review_count": str(biz.get("aggregateRating", {}).get("reviewCount", "")),
                        "location": location,
                        "niche": niche,
                        "source": "yelp",
                    })
                    if len(businesses) >= limit:
                        break
        except Exception:
            continue

    # Fallback: parse visible business cards from HTML
    if not businesses:
        # Yelp business names appear in <a> tags with /biz/ in href
        biz_links = re.findall(r'href="/biz/([^"?]+)"[^>]*>([^<]+)</a>', html)
        seen_slugs = set()
        for slug, text in biz_links:
            text = text.strip()
            if text and len(text) > 2 and slug not in seen_slugs and not text.startswith('<'):
                seen_slugs.add(slug)
                if text not in seen_names:
                    seen_names.add(text)
                    businesses.append({
                        "name": text,
                        "phone": "",
                        "address": location,
                        "website": "",
                        "location": location,
                        "niche": niche,
                        "source": "yelp",
                    })
                    if len(businesses) >= limit:
                        break

    print(f"[Yelp] Found {len(businesses)} businesses for '{niche}' in '{location}'")
    return businesses


# ─── SOURCE 3: Google Maps via Playwright (improved) ──────────────────────────

async def search_google_maps_playwright(niche: str, location: str, limit: int = 20) -> list:
    """
    Google Maps scraping with consent-page handling and JS data extraction.
    Uses semantic selectors (role=article, role=heading) not fragile CSS classes.
    """
    if not PLAYWRIGHT_AVAILABLE:
        return [{"error": "Playwright not installed"}]

    query = f"{niche} in {location}"
    url   = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
    results = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--disable-extensions",
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=_rand_ua(),
            locale="en-US",
            timezone_id="America/New_York",
        )
        # Remove webdriver property
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=35000)
            await asyncio.sleep(3)

            # Handle Google consent / cookie pages
            consent_selectors = [
                'button[aria-label*="Accept all"]',
                'button[aria-label*="Reject all"]',
                '#L2AGLb',
                '#W0wltc',
                'button.tHlp8d',
                'form[action*="consent.google"] button',
                '[data-value="1"] button',
            ]
            for sel in consent_selectors:
                try:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(2)
                        break
                except Exception:
                    pass

            await asyncio.sleep(2)

            # Scroll the results feed to load more
            for i in range(6):
                try:
                    # Try feed scroll first
                    await page.evaluate("""() => {
                        const feed = document.querySelector('[role="feed"]');
                        if (feed) feed.scrollTop += 800;
                        else window.scrollBy(0, 600);
                    }""")
                    await asyncio.sleep(1.2)
                except Exception:
                    pass

            # Extract listings via JavaScript
            # Google Maps structure: <a class="hfpxzc" aria-label="BUSINESS NAME" href="/maps/place/...">
            listings = await page.evaluate("""() => {
                const results = [];
                const seen = new Set();

                // PRIMARY: aria-label on the main clickable link (most reliable)
                document.querySelectorAll('a[href*="/maps/place/"][aria-label]').forEach(link => {
                    try {
                        const name = (link.getAttribute('aria-label') || '').trim();
                        const href = link.href || '';
                        if (name && name.length > 1 && name.length < 100 && !seen.has(name)
                            && href.includes('/maps/place/')) {
                            seen.add(name);
                            results.push({ name, href });
                        }
                    } catch(e) {}
                });

                // FALLBACK: role="article" with heading or text
                if (results.length < 3) {
                    document.querySelectorAll('[role="article"]').forEach(article => {
                        try {
                            const link = article.querySelector('a[href*="maps/place"]');
                            if (!link) return;
                            const heading = article.querySelector('[role="heading"]')
                                         || article.querySelector('h3')
                                         || article.querySelector('[class*="fontHeadline"]');
                            const name = heading ? heading.textContent.trim()
                                       : (link.getAttribute('aria-label') || '').trim();
                            if (name && name.length > 1 && !seen.has(name)) {
                                seen.add(name);
                                results.push({ name, href: link.href });
                            }
                        } catch(e) {}
                    });
                }

                return results;
            }""")

            seen_names = set()
            for item in listings:
                if len(results) >= limit:
                    break
                name = (item.get("name") or "").strip()
                href = item.get("href", "")
                if name and name not in seen_names and len(name) > 1:
                    seen_names.add(name)
                    results.append({
                        "name": name,
                        "maps_url": href,
                        "location": location,
                        "niche": niche,
                        "source": "google_maps",
                    })

            print(f"[Maps] Playwright found {len(results)} businesses")

        except Exception as e:
            print(f"[Maps] Playwright error: {e}")
            results = [{"error": f"Maps search failed: {e}"}]
        finally:
            await browser.close()

    return results


# ─── GBP AUDIT — Fast httpx check ─────────────────────────────────────────────

async def check_gbp_via_search(business_name: str, location: str) -> dict:
    """
    Check GBP completeness by scraping a targeted Google search result.
    Much faster than loading the full Maps page — one HTTP request per business.
    """
    query = '"' + business_name + '" ' + location
    q_encoded = query.replace(' ', '+').replace('"', '%22')
    url   = f"https://www.google.com/search?q={q_encoded}&gl=us&hl=en&num=5"

    try:
        async with httpx.AsyncClient(
            headers=_http_headers(), follow_redirects=True, timeout=15
        ) as client:
            resp = await client.get(url)
            html = resp.text
    except Exception as e:
        return {
            "error": str(e), "has_gbp": False, "score": 5,
            "issues": ["Could not check GBP — network error"],
            "priority": "WARM", "issue_count": 1, "found": {}
        }

    issues = []
    found  = {}
    name_lower = business_name.lower()

    # ── Does a Knowledge Panel / local result appear? ──
    kp_signals = [
        'data-attrid="kc:/local:',
        'data-local-attribute',
        '"LocalBusiness"',
        'kp-wholepage',
        'kc:/location/location:',
        'action="https://www.google.com/maps',
        'Maps result',
        '/maps/place/',
    ]
    has_kp = any(sig in html for sig in kp_signals)

    if not has_kp:
        # Check if the business name even appears in results
        name_present = name_lower[:12] in html.lower() if len(name_lower) >= 12 else name_lower in html.lower()
        if not name_present:
            issues.append("NO GBP LISTING FOUND — biggest opportunity")
            return {
                "has_gbp": False, "score": 0, "issues": issues,
                "found": found, "priority": "HOT", "issue_count": len(issues)
            }
        else:
            issues.append("No Google Business Profile visible in search results")
            found["has_gbp"] = False
    else:
        found["has_gbp"] = True

    # ── Phone number ──
    phone_m = re.search(r'\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}', html)
    if phone_m:
        found["phone"] = phone_m.group(0).strip()
    else:
        issues.append("Phone number not visible on Google listing")

    # ── Business hours ──
    hours_signals = ['open now', 'closed now', 'opens at', 'closes at',
                     'open ·', 'closed ·', 'hours', '24 hours']
    if any(sig in html.lower() for sig in hours_signals):
        found["has_hours"] = True
    else:
        issues.append("Business hours not listed on Google")

    # ── Website ──
    if re.search(r'href="https?://(?!www\.google)[^"]+"\s[^>]*>(?:Website|Visit site)', html, re.IGNORECASE):
        found["has_website"] = True
    elif '.com' in html and 'website' in html.lower():
        found["has_website"] = True
    else:
        issues.append("No website linked to Google Business Profile")

    # ── Reviews ──
    rev_m = re.search(r'([\d,]+)\s*(?:Google\s*)?review', html, re.IGNORECASE)
    if rev_m:
        count = int(rev_m.group(1).replace(',', ''))
        found["review_count"] = count
        if count < 5:
            issues.append(f"Very few reviews ({count}) — needs review strategy")
    else:
        issues.append("No reviews visible — possibly unclaimed or brand new")

    # ── Rating ──
    rating_m = re.search(r'(\d\.\d)\s*(?:stars?\s*)?(?:·|\()', html)
    if rating_m:
        found["rating"] = rating_m.group(1)

    # ── Photos ──
    if 'photo' not in html.lower():
        issues.append("No photos visible in Google listing")

    # ── Description / posts ──
    if 'description' not in html.lower() and 'about' not in html.lower():
        if len(issues) < 6:  # Don't pile on if already has many issues
            issues.append("No business description or Google Posts")

    # ── Unclaimed? ──
    if 'own this business' in html.lower() or 'claim this business' in html.lower():
        issues.append("UNCLAIMED listing — owner has NOT verified it")
        found["unclaimed"] = True

    score    = max(0.0, round(10 - len(issues) * 1.5, 1))
    priority = "COLD"
    if score <= 3 or not found.get("has_gbp") or found.get("unclaimed"):
        priority = "HOT"
    elif score <= 6:
        priority = "WARM"

    return {
        "has_gbp": found.get("has_gbp", False),
        "score": score,
        "issues": issues,
        "found": found,
        "priority": priority,
        "issue_count": len(issues),
    }


async def audit_gbp_from_maps_url(maps_url: str, business_name: str) -> dict:
    """
    Visit a Maps place URL directly via Playwright to get real GBP data.
    Use this when we already found the business ON Google Maps (they clearly have a GBP).
    Extracts: phone, website, hours, review count, rating, photos, unclaimed status.
    """
    if not PLAYWRIGHT_AVAILABLE or not maps_url:
        return {"has_gbp": True, "score": 5.0, "issues": ["Could not audit — Playwright unavailable"],
                "found": {}, "priority": "WARM", "issue_count": 1}

    issues = []
    found  = {"has_gbp": True}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=_rand_ua(), locale="en-US",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = await context.new_page()

        try:
            await page.goto(maps_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # Handle consent pages
            for sel in ['button[aria-label*="Accept all"]', '#L2AGLb', '#W0wltc']:
                try:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(2)
                        break
                except Exception:
                    pass

            # Extract all data via JavaScript
            data = await page.evaluate("""() => {
                const getText = (sel) => {
                    const el = document.querySelector(sel);
                    return el ? el.textContent.trim() : '';
                };
                const getAttr = (sel, attr) => {
                    const el = document.querySelector(sel);
                    return el ? (el.getAttribute(attr) || '') : '';
                };

                // Phone
                const phoneEl = document.querySelector('button[data-item-id*="phone"], [aria-label*="Phone:"], [data-tooltip*="phone"]');
                const phone = phoneEl ? phoneEl.textContent.trim() : '';

                // Website
                const webEl = document.querySelector('a[data-item-id="authority"], [aria-label*="website" i], [data-tooltip*="website" i]');
                const website = webEl ? (webEl.href || webEl.textContent.trim()) : '';

                // Hours
                const hasHours = !!(document.querySelector('[data-item-id*="oh"], [aria-label*="hour" i]') ||
                                    document.body.innerHTML.includes('Open') ||
                                    document.body.innerHTML.includes('Closed'));

                // Review count + rating
                const reviewText = getText('[data-attrid*="review"] span, .fontBodySmall');
                const reviewMatch = document.body.innerHTML.match(/([\d,]+)\s*review/i);
                const reviewCount = reviewMatch ? parseInt(reviewMatch[1].replace(',','')) : 0;

                const ratingMatch = document.body.innerHTML.match(/(\d\.\d)\s*(?:stars?)?/);
                const rating = ratingMatch ? ratingMatch[1] : '';

                // Photos
                const photoMatch = document.body.innerHTML.match(/(\d+)\s*photo/i);
                const photoCount = photoMatch ? parseInt(photoMatch[1]) : 0;
                const hasPhotos = photoCount > 0 || document.body.innerHTML.toLowerCase().includes('photo');

                // Unclaimed
                const unclaimed = document.body.innerHTML.toLowerCase().includes('own this business') ||
                                  document.body.innerHTML.toLowerCase().includes('claim this business');

                // Description
                const hasDesc = document.body.innerHTML.toLowerCase().includes('about') ||
                                document.body.innerHTML.toLowerCase().includes('description');

                // Posts / updates
                const hasPosts = document.body.innerHTML.toLowerCase().includes('update') ||
                                 document.body.innerHTML.toLowerCase().includes('post');

                return { phone, website, hasHours, reviewCount, rating,
                         hasPhotos, photoCount, unclaimed, hasDesc, hasPosts };
            }""")

            if data.get("phone"):
                found["phone"] = data["phone"]
            else:
                issues.append("Phone number missing from Google listing")

            if data.get("website"):
                found["website"] = data["website"]
            else:
                issues.append("No website linked to Google Business Profile")

            if data.get("hasHours"):
                found["has_hours"] = True
            else:
                issues.append("Business hours not set on Google listing")

            review_count = data.get("reviewCount", 0)
            found["review_count"] = review_count
            if review_count == 0:
                issues.append("No reviews — needs review strategy urgently")
            elif review_count < 10:
                issues.append(f"Very few reviews ({review_count}) — missing revenue from low trust")

            if data.get("rating"):
                found["rating"] = data["rating"]

            if not data.get("hasPhotos"):
                issues.append("No photos on Google listing — kills conversion rate")
            elif data.get("photoCount", 0) < 5:
                issues.append(f"Only {data.get('photoCount')} photos — needs more visual content")

            if data.get("unclaimed"):
                issues.append("UNCLAIMED — owner has never verified this listing!")
                found["unclaimed"] = True

            if not data.get("hasDesc"):
                issues.append("No business description — missing keywords and trust signals")

            if not data.get("hasPosts"):
                issues.append("No Google Posts — not engaging with potential customers")

        except Exception as e:
            print(f"[GBP Audit] Maps page error for {business_name}: {e}")
            # Still mark as having a GBP since we found it on Maps
            issues.append("Could not fully audit — profile needs manual review")
        finally:
            await browser.close()

    score    = max(0.0, round(10 - len(issues) * 1.5, 1))
    priority = "COLD"
    if score <= 3 or found.get("unclaimed"):
        priority = "HOT"
    elif score <= 6:
        priority = "WARM"

    return {
        "has_gbp": True,
        "score": score,
        "issues": issues,
        "found": found,
        "priority": priority,
        "issue_count": len(issues),
    }


async def audit_gbp(business_name: str, location: str, maps_url: str = "") -> dict:
    """Public API — audit a business's GBP completeness."""
    if maps_url and "google.com/maps/place" in maps_url:
        # Found on Maps = has GBP. Audit the actual listing page.
        return await audit_gbp_from_maps_url(maps_url, business_name)
    else:
        # Unknown source — use Google search check
        return await check_gbp_via_search(business_name, location)


# ─── MAIN PIPELINE ─────────────────────────────────────────────────────────────

async def search_google_maps(niche: str, location: str, limit: int = 20) -> list:
    """
    Find businesses — tries sources in order of reliability:
    1. Yellow Pages (primary — best for phone numbers)
    2. Yelp (secondary — better for service businesses)
    3. Google Maps Playwright (fallback)
    """
    # Try Yellow Pages first
    print(f"[GBP] Trying Yellow Pages: {niche} in {location}")
    results = await search_yellowpages(niche, location, limit)
    valid = [r for r in results if "error" not in r]
    if len(valid) >= 5:
        print(f"[GBP] Yellow Pages success: {len(valid)} businesses")
        return valid

    # Try Yelp
    print(f"[GBP] Trying Yelp: {niche} in {location}")
    await _human_delay(1000, 2000)
    results = await search_yelp(niche, location, limit)
    valid = [r for r in results if "error" not in r]
    if len(valid) >= 3:
        print(f"[GBP] Yelp success: {len(valid)} businesses")
        return valid

    # Fallback to Google Maps Playwright
    print(f"[GBP] Falling back to Google Maps Playwright...")
    results = await search_google_maps_playwright(niche, location, limit)
    return results


async def run_prospect_scan(niche: str, location: str, limit: int = 15) -> list:
    """
    Full pipeline: find businesses → score their GBP → return HOT and WARM prospects.
    These are real businesses with real phone numbers Katy can call.
    """
    print(f"\n[GBP Audit] ═══ SCANNING: {niche} in {location} ═══")
    businesses = await search_google_maps(niche, location, limit=limit)

    # Filter out error results
    valid = [b for b in businesses if "error" not in b]
    if not valid:
        error = businesses[0].get("error", "no businesses found") if businesses else "no results"
        print(f"[GBP Audit] ERROR: {error}")
        return [{"error": error}]

    print(f"[GBP Audit] Found {len(valid)} businesses — auditing GBP quality...")

    prospects = []
    for biz in valid:
        biz_name = biz.get("name", "")
        maps_url  = biz.get("maps_url", "")
        print(f"[GBP Audit] Auditing: {biz_name}...")

        # Use maps_url audit (Playwright) for businesses found on Maps — gets real phone + issues
        # Use search-based audit for businesses from YP/Yelp (no maps_url)
        if maps_url and "google.com/maps/place" in maps_url:
            audit = await audit_gbp_from_maps_url(maps_url, biz_name)
        else:
            audit = await check_gbp_via_search(biz_name, biz.get("location", location))

        await asyncio.sleep(random.uniform(0.3, 0.8))

        # Accept businesses found on Maps (they have a GBP but may need optimization)
        # OR businesses with 2+ issues from search audit
        from_maps = biz.get("source") == "google_maps"
        has_issues = audit.get("issue_count", 0) >= 2
        no_gbp = not audit.get("has_gbp", True)

        if from_maps or has_issues or no_gbp:
            prospect = {**biz, **audit}

            # Promote phone from YP/Yelp if found dict doesn't have one
            yp_phone = biz.get("phone", "")
            maps_phone = prospect.get("found", {}).get("phone", "")
            if yp_phone and not maps_phone:
                prospect.setdefault("found", {})["phone"] = yp_phone

            prospects.append(prospect)
            issues_preview = "; ".join(audit.get("issues", [])[:2])
            phone_status = "📞 " + (prospect.get("found", {}).get("phone") or "no phone yet")
            print(
                f"[GBP Audit] ✓ PROSPECT: {biz_name} | "
                f"Score {audit['score']}/10 | {audit['priority']} | {phone_status} | {issues_preview}"
            )
        else:
            print(f"[GBP Audit]   skip: {biz_name} (GBP looks complete, score {audit.get('score', '?')})")

    # Sort: HOT first, then WARM, then COLD
    order = {"HOT": 0, "WARM": 1, "COLD": 2}
    prospects.sort(key=lambda p: order.get(p.get("priority", "COLD"), 2))

    print(f"[GBP Audit] ═══ COMPLETE: {len(prospects)} prospects found ═══\n")
    return prospects
