"""Câblage du moteur autonome au reste de server.py (browser partagé + verrou)."""
import asyncio


def make_scrape_fn(get_context, extract_fn, scrape_lock: asyncio.Lock):
    """Fabrique un scrape_fn(url) qui réutilise le Chromium partagé, sérialisé par un verrou.

    get_context: coroutine() -> contexte Playwright (browser partagé)
    extract_fn:  coroutine(page) -> list[ad]   (= engine.scraper.extract_ads_from_results)
    scrape_lock: asyncio.Lock pour ne jamais naviguer en parallèle (manuel vs auto)
    """
    async def scrape_fn(url: str) -> list:
        async with scrape_lock:
            context = await get_context()
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded")
                await page.wait_for_timeout(1500)
                return await extract_fn(page)
            finally:
                await page.close()
    return scrape_fn
