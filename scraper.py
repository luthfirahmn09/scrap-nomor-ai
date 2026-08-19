from __future__ import annotations

import asyncio
import logging
import re
from typing import Callable, Coroutine, Optional

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

SOCIAL_MEDIA_DOMAINS = [
    "instagram.com",
    "facebook.com",
    "fb.com",
    "fb.me",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "youtube.com",
    "linkedin.com",
]

# Indonesian phone pattern
_PHONE_RE = re.compile(r"(?:\+62|62|0)[.\-\s]?\d{2,4}[.\-\s]?\d{3,5}[.\-\s]?\d{3,5}")


def is_social_media(url: str) -> bool:
    return any(d in url.lower() for d in SOCIAL_MEDIA_DOMAINS)


def should_include(website: str) -> bool:
    if not website:
        return True
    return is_social_media(website)


async def _extract_phone(page) -> str:
    # 1. data-item-id attribute (classic)
    el = await page.query_selector('[data-item-id^="phone:"]')
    if el:
        item_id = await el.get_attribute("data-item-id") or ""
        phone = item_id.replace("phone:", "").strip()
        if phone:
            logger.debug(f"Phone via data-item-id: {phone}")
            return phone

    # 2. aria-label on any button containing phone pattern
    buttons = await page.query_selector_all("button[aria-label], [role='button'][aria-label]")
    for btn in buttons:
        label = await btn.get_attribute("aria-label") or ""
        match = _PHONE_RE.search(label)
        if match:
            logger.debug(f"Phone via aria-label: {match.group(0)}")
            return match.group(0).strip()

    # 3. Scan full page text in main panel
    panel = await page.query_selector('[role="main"]')
    if panel:
        text = await panel.inner_text()
        match = _PHONE_RE.search(text)
        if match:
            logger.debug(f"Phone via text scan: {match.group(0)}")
            return match.group(0).strip()

    logger.debug("Phone: not found")
    return ""


async def _extract_website(page) -> str:
    # 1. data-item-id="authority"
    el = await page.query_selector('a[data-item-id="authority"]')
    if el:
        href = await el.get_attribute("href") or ""
        if href:
            return href

    # 2. Any external link inside main panel with aria-label hint
    panel = await page.query_selector('[role="main"]')
    if panel:
        links = await panel.query_selector_all("a[href^='http']")
        for link in links:
            href = await link.get_attribute("href") or ""
            aria = (await link.get_attribute("aria-label") or "").lower()
            if not href:
                continue
            # Skip Google-owned URLs
            if any(g in href for g in ["google.com", "goo.gl", "googleapis"]):
                continue
            # Prefer links with website/situs label
            if "website" in aria or "situs" in aria or "web" in aria:
                return href
        # Fallback: first non-Google external link
        for link in links:
            href = await link.get_attribute("href") or ""
            if href and not any(g in href for g in ["google.com", "goo.gl", "googleapis"]):
                return href

    return ""


async def scrape_maps(
    keyword: str,
    max_results: int = 30,
    headless: bool = True,
    progress_cb: Optional[Callable[[int, int], Coroutine]] = None,
) -> list[dict]:
    results: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="id-ID",
        )
        page = await ctx.new_page()

        try:
            search_url = f"https://www.google.com/maps/search/{keyword.replace(' ', '+')}"
            logger.info(f"Opening: {search_url}")
            await page.goto(search_url, wait_until="networkidle", timeout=30000)

            # Handle consent/cookie popup if present
            try:
                accept = page.locator('button:has-text("Accept all"), button:has-text("Terima semua")')
                if await accept.count():
                    await accept.first.click()
                    await asyncio.sleep(1)
            except Exception:
                pass

            # Single result page (no feed)
            try:
                await page.wait_for_selector('[role="feed"]', timeout=10000)
            except PlaywrightTimeoutError:
                logger.warning("No feed — trying single result extraction")
                await asyncio.sleep(2)
                result = await _extract_one(page)
                if result:
                    logger.info(f"Single result: {result}")
                    if should_include(result.get("website", "")):
                        results.append(result)
                return results

            # Scroll to collect listing links
            listing_urls: list[str] = []
            seen: set[str] = set()

            for scroll_i in range(20):
                await page.evaluate(
                    "const f = document.querySelector('[role=\"feed\"]'); if(f) f.scrollBy(0,800);"
                )
                await asyncio.sleep(1.5)

                hrefs: list[str] = await page.eval_on_selector_all(
                    '[role="feed"] a[href*="/maps/place/"]',
                    "els => els.map(e => e.href)",
                )
                for href in hrefs:
                    base = href.split("?")[0]
                    if base not in seen:
                        seen.add(base)
                        listing_urls.append(href)

                if len(listing_urls) >= max_results:
                    break

                # Check end-of-list marker
                end_el = await page.query_selector(
                    "span:has-text('Anda telah mencapai akhir'), span:has-text(\"You've reached the end\")"
                )
                if end_el:
                    logger.info("Reached end of results")
                    break

            listing_urls = listing_urls[:max_results]
            logger.info(f"Found {len(listing_urls)} listings for '{keyword}'")

            for i, url in enumerate(listing_urls):
                try:
                    if progress_cb:
                        await progress_cb(i + 1, len(listing_urls))

                    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    # Wait for detail panel to render
                    try:
                        await page.wait_for_selector("h1", timeout=8000)
                    except PlaywrightTimeoutError:
                        pass
                    await asyncio.sleep(1.5)

                    name_el = await page.query_selector("h1")
                    name = (await name_el.inner_text()).strip() if name_el else ""

                    phone = await _extract_phone(page)
                    website = await _extract_website(page)

                    if not should_include(website):
                        logger.info(f"Skip '{name}' — real website: {website}")
                        continue

                    maps_url = page.url.split("?")[0]
                    if "/maps/place/" not in maps_url:
                        maps_url = url.split("?")[0]

                    entry = {
                        "nama": name,
                        "no_telepon": phone,
                        "email": "",
                        "link_google_maps": maps_url,
                        "website": website,
                    }
                    results.append(entry)
                    logger.info(f"OK [{i+1}] {name} | {phone or 'NO PHONE'} | {website or 'NO WEB'}")

                except Exception as e:
                    logger.warning(f"Error listing {i+1}: {e}")

        finally:
            await browser.close()

    return results


async def _extract_one(page) -> Optional[dict]:
    try:
        name_el = await page.query_selector("h1")
        name = (await name_el.inner_text()).strip() if name_el else ""
        phone = await _extract_phone(page)
        website = await _extract_website(page)
        maps_url = page.url.split("?")[0]
        return {"nama": name, "no_telepon": phone, "email": "", "link_google_maps": maps_url, "website": website}
    except Exception as e:
        logger.warning(f"Single extract failed: {e}")
        return None
