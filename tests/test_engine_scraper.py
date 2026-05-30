import pytest
from playwright.async_api import async_playwright
from engine.scraper import extract_ads_from_results

FIXTURE_HTML = """
<html><body>
<ul>
  <li>
    <a data-qa-id="aditem_container" href="/ad/consoles_jeux_video/2912345678">
      <p data-qa-id="aditem_title">PS5 Slim</p>
      <span data-qa-id="aditem_price">250 €</span>
      <p data-qa-id="aditem_location">Bordeaux 33000</p>
      <img src="https://img.leboncoin.fr/a.jpg"/>
    </a>
  </li>
  <li>
    <a data-qa-id="aditem_container" href="/ad/informatique/2999000111">
      <p data-qa-id="aditem_title">PC portable</p>
      <span data-qa-id="aditem_price">1 200 €</span>
      <p data-qa-id="aditem_location">Lyon 69000</p>
      <img src="https://img.leboncoin.fr/b.jpg"/>
    </a>
  </li>
</ul>
</body></html>
"""


async def test_extract_ads_from_results_parses_fixture():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(FIXTURE_HTML)
        ads = await extract_ads_from_results(page)
        await browser.close()

    assert len(ads) == 2
    first = ads[0]
    assert first["ad_id"] == "2912345678"
    assert first["title"] == "PS5 Slim"
    assert first["price"] == 250.0
    assert first["city"] == "Bordeaux 33000"
    assert first["url"] == "https://www.leboncoin.fr/ad/consoles_jeux_video/2912345678"
    assert first["image_url"] == "https://img.leboncoin.fr/a.jpg"
    assert ads[1]["price"] == 1200.0
