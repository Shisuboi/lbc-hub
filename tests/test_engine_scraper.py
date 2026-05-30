import pytest
from playwright.async_api import async_playwright
from engine.scraper import extract_ads_from_results

# Structure réelle Leboncoin (2026) : cartes <article aria-label="titre"> contenant
# un lien /ad/, une image (?rule=ad-image), un <span> de prix, et un libellé
# d'accessibilité « Située à <ville>. ». Plus de data-qa-id pour titre/prix/ville.
FIXTURE_HTML = """
<html><body>
<article aria-label="PS5 Slim">
  <div data-qa-id="aditem_container">
    <a class="absolute inset-0" href="/ad/consoles_jeux_video/2912345678">
      <span title="Voir l'annonce: PS5 Slim"></span>
    </a>
    <picture><img src="https://img.leboncoin.fr/api/v1/lbcpb1/images/a.jpg?rule=ad-image" alt=""></picture>
    <span>250 &euro;</span>
    <p class="sr-only">Prix: 250 &euro;.</p>
    <p class="sr-only">Située à Bordeaux 33000.</p>
  </div>
</article>
<article aria-label="PC portable">
  <div data-qa-id="aditem_container">
    <a class="absolute inset-0" href="/ad/informatique/2999000111">
      <span title="Voir l'annonce: PC portable"></span>
    </a>
    <picture><img src="https://img.leboncoin.fr/api/v1/lbcpb1/images/b.jpg?rule=ad-image" alt=""></picture>
    <span>1 200 &euro;</span>
    <p class="sr-only">Située à Lyon 69000.</p>
  </div>
</article>
</body></html>
"""

# Carte avec un avatar vendeur (pp-small) AVANT la vraie photo : on doit ignorer l'avatar.
AVATAR_HTML = """
<html><body>
<article aria-label="Ordinateur gamer">
  <div data-qa-id="aditem_container">
    <a class="absolute inset-0" href="/ad/ordinateurs/3196142185"><span title="Voir l'annonce: Ordinateur gamer"></span></a>
    <img src="https://img.leboncoin.fr/api/v1/tenants/x/profile/pictures/default/abc?rule=pp-small" alt="">
    <img src="https://img.leboncoin.fr/api/v1/lbcpb1/images/real.jpg?rule=ad-image" alt="">
    <span>550 &euro;</span>
    <p class="sr-only">Située à Vitry-sur-Seine 94400.</p>
  </div>
</article>
</body></html>
"""

DUP_HTML = """
<html><body>
<article aria-label="PS5 A">
  <a href="/ad/consoles/2912345678"><span title="Voir l'annonce: PS5 A"></span></a>
  <span>250 &euro;</span>
</article>
<article aria-label="PS5 A bis">
  <a href="/ad/consoles/2912345678/?ref=foo"><span title="Voir l'annonce: PS5 A bis"></span></a>
  <span>250 &euro;</span>
</article>
</body></html>
"""

OFFDOMAIN_HTML = """
<html><body>
<article aria-label="Arnaque">
  <a href="https://evil.example.com/ad/steal/9999999999"><span title="x"></span></a>
  <span>10 &euro;</span>
</article>
<article aria-label="PS5 legit">
  <a href="/ad/consoles/2912345678"><span title="x"></span></a>
  <span>250 &euro;</span>
</article>
</body></html>
"""


async def _extract(html):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html)
        ads = await extract_ads_from_results(page)
        await browser.close()
    return ads


async def test_extract_ads_from_results_parses_fixture():
    ads = await _extract(FIXTURE_HTML)

    assert len(ads) == 2
    first = ads[0]
    assert first["ad_id"] == "2912345678"
    assert first["title"] == "PS5 Slim"
    assert first["price"] == 250.0
    assert first["city"] == "Bordeaux 33000"
    assert first["url"] == "https://www.leboncoin.fr/ad/consoles_jeux_video/2912345678"
    assert first["image_url"].endswith("a.jpg?rule=ad-image")
    assert ads[1]["price"] == 1200.0
    assert ads[1]["title"] == "PC portable"
    assert ads[1]["city"] == "Lyon 69000"


async def test_extract_ignores_seller_avatar_image():
    ads = await _extract(AVATAR_HTML)
    assert len(ads) == 1
    # l'avatar pp-small est ignoré ; on garde la vraie photo ?rule=ad-image
    assert ads[0]["image_url"].endswith("real.jpg?rule=ad-image")
    assert ads[0]["price"] == 550.0


async def test_extract_dedups_same_ad_id():
    ads = await _extract(DUP_HTML)
    assert len(ads) == 1
    assert ads[0]["ad_id"] == "2912345678"


async def test_extract_excludes_off_domain_links():
    ads = await _extract(OFFDOMAIN_HTML)
    assert len(ads) == 1
    assert ads[0]["ad_id"] == "2912345678"
    assert ads[0]["url"].startswith("https://www.leboncoin.fr/")


async def test_extract_empty_page_returns_empty_list():
    ads = await _extract("<html><body><p>rien</p></body></html>")
    assert ads == []
