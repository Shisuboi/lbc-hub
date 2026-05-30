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
            print(f"🔎 [AUTO] Onglet ouvert, navigation vers : {url[:90]}")
            try:
                await page.goto(url, wait_until="domcontentloaded")
                print("🔎 [AUTO] Page chargée (domcontentloaded).")
                if ready_selector:
                    try:
                        await page.wait_for_selector(ready_selector, timeout=ready_timeout_ms)
                        print("🔎 [AUTO] Annonces détectées immédiatement.")
                    except Exception as exc:
                        # Pas d'annonces tout de suite : blocage Datadome probable.
                        # On garde l'onglet ouvert et on laisse à l'humain le temps de résoudre.
                        print(
                            f"⚠️ [AUTO] Pas d'annonces après {ready_timeout_ms} ms "
                            f"({type(exc).__name__}). Blocage/captcha probable — résous-le dans "
                            "la fenêtre Chromium (attente jusqu'à 2 min)..."
                        )
                        try:
                            await page.wait_for_selector(ready_selector, timeout=captcha_wait_ms)
                            print("✅ [AUTO] Page débloquée, extraction en cours.")
                        except Exception as exc2:
                            print(
                                f"⏭️ [AUTO] Toujours pas d'annonces ({type(exc2).__name__}) — "
                                "passage à la recherche suivante."
                            )
                else:
                    await page.wait_for_timeout(1500)
                ads = await extract_fn(page)
                print(f"🔎 [AUTO] Extraction terminée : {len(ads)} annonce(s) trouvée(s).")
                return ads
            except Exception as exc:
                print(f"🔴 [AUTO] Erreur pendant le scrape ({type(exc).__name__}): {exc}")
                raise
            finally:
                print("🔎 [AUTO] Fermeture de l'onglet.")
                await page.close()
    return scrape_fn
