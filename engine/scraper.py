"""Extraction des annonces depuis une page de RÉSULTATS Leboncoin (pas de page détail).

On ne lit que ce que la liste expose déjà : id, titre, prix, ville, miniature, URL.
"""
from urllib.parse import urljoin
from engine.parse import extract_ad_id, clean_price

_BASE = "https://www.leboncoin.fr"
_CONTAINER_SEL = 'a[data-qa-id="aditem_container"], a[href*="/ad/"]'


async def extract_ads_from_results(page) -> list[dict]:
    """Retourne une liste d'annonces depuis la page de résultats déjà chargée."""
    ads: list[dict] = []
    seen_ids: set[str] = set()
    containers = await page.query_selector_all(_CONTAINER_SEL)

    for el in containers:
        href = await el.get_attribute("href")
        if not href or "/ad/" not in href:
            continue
        url = urljoin(_BASE, href)
        ad_id = extract_ad_id(url)
        if not ad_id or ad_id in seen_ids:
            continue
        seen_ids.add(ad_id)

        title_el = await el.query_selector('[data-qa-id="aditem_title"], p[data-test-id="adcard-title"]')
        price_el = await el.query_selector('[data-qa-id="aditem_price"], span[data-test-id="price"]')
        loc_el = await el.query_selector('[data-qa-id="aditem_location"]')
        img_el = await el.query_selector("img")

        title = (await title_el.inner_text()).strip() if title_el else ""
        price = clean_price(await price_el.inner_text()) if price_el else 0.0
        city = (await loc_el.inner_text()).strip() if loc_el else None
        image_url = (await img_el.get_attribute("src")) if img_el else None

        ads.append({
            "ad_id": ad_id,
            "title": title,
            "price": price,
            "url": url,
            "city": city,
            "image_url": image_url,
        })

    return ads
