"""Câblage du moteur autonome au reste de server.py (browser partagé + verrou)."""
import asyncio


def make_scrape_fn(
    get_context,
    extract_fn,
    scrape_lock: asyncio.Lock,
    ready_selector: str | None = None,
    ready_timeout_ms: int = 8000,
    captcha_wait_ms: int = 120000,
):
    """Fabrique un scrape_fn(url) qui réutilise le Chromium partagé, sérialisé par un verrou.

    get_context: coroutine() -> contexte Playwright (browser partagé)
    extract_fn:  coroutine(page) -> list[ad]   (= engine.scraper.extract_ads_from_results)
    scrape_lock: asyncio.Lock pour ne jamais naviguer en parallèle (manuel vs auto)
    ready_selector: sélecteur CSS attendu sur une page de résultats prête. Si fourni,
        on l'attend avant d'extraire — ce qui LAISSE L'ONGLET OUVERT pour résoudre un
        captcha Datadome à la main. Si None : ancien comportement (attente fixe courte).
    ready_timeout_ms: délai d'attente initial (page normale prête en quelques secondes).
    captcha_wait_ms: délai d'attente prolongé après un blocage probable (résolution manuelle).
    """
    async def scrape_fn(url: str) -> list:
        async with scrape_lock:
            context = await get_context()
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded")
                if ready_selector:
                    try:
                        await page.wait_for_selector(ready_selector, timeout=ready_timeout_ms)
                    except Exception:
                        # Pas d'annonces tout de suite : blocage Datadome probable.
                        # On garde l'onglet ouvert et on laisse à l'humain le temps de résoudre.
                        print(
                            "⚠️ [AUTO] Blocage/captcha probable — résous-le dans la fenêtre "
                            "Chromium ouverte (attente jusqu'à 2 min)..."
                        )
                        try:
                            await page.wait_for_selector(ready_selector, timeout=captcha_wait_ms)
                            print("✅ [AUTO] Page débloquée, extraction en cours.")
                        except Exception:
                            print("⏭️ [AUTO] Toujours pas d'annonces — passage à la recherche suivante.")
                else:
                    await page.wait_for_timeout(1500)
                return await extract_fn(page)
            finally:
                await page.close()
    return scrape_fn
