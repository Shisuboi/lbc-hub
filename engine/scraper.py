"""Extraction des annonces depuis une page de RÉSULTATS Leboncoin (pas de page détail).

Leboncoin n'expose plus de `data-qa-id` stables pour titre/prix/ville : on lit donc la
structure actuelle (cartes ``<article>``) via un script DOM exécuté dans la page. On
s'appuie sur la sémantique stable (``article[aria-label]`` = titre, ``a[href*="/ad/"]`` =
URL, texte du prix terminé par « € », libellé d'accessibilité « Située à … » = ville)
plutôt que sur les classes utilitaires (Tailwind) qui changent souvent.
"""
from urllib.parse import urljoin, urlparse
from engine.parse import extract_ad_id, clean_price

_BASE = "https://www.leboncoin.fr"
_ALLOWED_HOSTS = {"www.leboncoin.fr", "leboncoin.fr"}
# Sélecteur de « page prête » : présence d'au moins un lien d'annonce. Utilisé par le
# moteur auto pour attendre le chargement (et distinguer un blocage Datadome).
RESULTS_CONTAINER_SELECTOR = 'a[href*="/ad/"]'

# Script exécuté DANS la page : retourne les champs bruts pour chaque carte <article>.
_EXTRACT_JS = r"""
() => {
  const ads = [];
  for (const art of document.querySelectorAll('article')) {
    const a = art.querySelector('a[href*="/ad/"]');
    if (!a) continue;
    const href = a.getAttribute('href') || '';

    // Titre : aria-label de l'article (fallback : attribut title du span overlay).
    let title = art.getAttribute('aria-label') || '';
    if (!title) {
      const sp = art.querySelector('span[title]');
      if (sp) title = (sp.getAttribute('title') || '').replace(/^Voir l.annonce\s*:?\s*/i, '');
    }

    // Prix : 1er élément dont le TEXTE PROPRE contient des chiffres suivis de « € ».
    let priceText = '';
    for (const el of art.querySelectorAll('span, p')) {
      const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('');
      if (/\d[\d\s  .,]*€/.test(own)) { priceText = own.trim(); break; }
    }

    // Ville : libellé d'accessibilité « Située à <ville>. ».
    let cityText = '';
    for (const el of art.querySelectorAll('p, span')) {
      const m = (el.textContent || '').trim().match(/^Situ[ée]+\s+à\s+(.+?)\.?$/i);
      if (m) { cityText = m[1].trim(); break; }
    }

    // Image : on évite les avatars de profil vendeur (pp-small / profile/pictures).
    let img = '';
    for (const im of art.querySelectorAll('img')) {
      const s = im.getAttribute('src') || '';
      if (s && !/pp-small|profile\/pictures/.test(s)) { img = s; break; }
    }

    ads.push({ href, title, priceText, cityText, img });
  }
  return ads;
}
"""


async def extract_ads_from_results(page) -> list[dict]:
    """Retourne une liste d'annonces depuis la page de résultats déjà chargée."""
    raw = await page.evaluate(_EXTRACT_JS)
    ads: list[dict] = []
    seen_ids: set[str] = set()

    for r in raw or []:
        url = urljoin(_BASE, r.get("href") or "")
        if urlparse(url).netloc.lower() not in _ALLOWED_HOSTS:
            continue
        ad_id = extract_ad_id(url)
        if not ad_id or ad_id in seen_ids:
            continue
        seen_ids.add(ad_id)
        ads.append({
            "ad_id": ad_id,
            "title": (r.get("title") or "").strip(),
            "price": clean_price(r.get("priceText") or ""),
            "url": url,
            "city": (r.get("cityText") or "").strip() or None,
            "image_url": (r.get("img") or "").strip() or None,
        })

    return ads
