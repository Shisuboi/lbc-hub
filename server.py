import asyncio
import json
import re
import os
import sys
import unicodedata
from aiohttp import web
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from playwright.async_api import async_playwright

# Force UTF-8 on stdout/stderr to support emojis on Windows terminals
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# --- GLOBAL JOB STATE ---

class ScraperJobState:
    def __init__(self):
        # idle → scraping → captcha_required → scraped (raw ads ready for external IA)
        # OR : scraped → completed (after JSON import of analyzed ads, ready to publish)
        # OR : error
        self.status = "idle"
        self.logs = []
        self.results = []
        self.total = 0  # nombre total d'annonces à analyser (pour le compteur en direct)
        self.task = None
        self.captcha_event = asyncio.Event()
        self.stop_event = asyncio.Event()
        self.clients = set()  # Active SSE client queues

    def log(self, message: str):
        print(message)
        self.logs.append(message)
        self.broadcast({"type": "log", "message": message})

    def set_status(self, status: str):
        self.status = status
        self.broadcast({"type": "status", "status": status})

    def broadcast(self, data: dict):
        for q in list(self.clients):
            try:
                q.put_nowait(data)
            except Exception:
                pass

job_state = ScraperJobState()

# --- 1. PLAYWRIGHT SCRAPING UTILS ---

def clean_price(price_text: str) -> float:
    """Parse a price string with French formatting (narrow no-break spaces, non-breaking spaces, etc.)."""
    # Normalize all Unicode whitespace to regular space, then strip non-numeric/non-dot
    cleaned = unicodedata.normalize('NFKD', price_text)
    # Remove everything except digits, dots, and commas
    cleaned = re.sub(r'[^\d.,]', '', cleaned)
    # Handle French decimal comma (e.g. '1000,50' -> '1000.50')
    cleaned = cleaned.replace(',', '.')
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0

async def get_ad_details(page, url):
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # Datadome check loop for detail page
        captcha_detected = False
        while True:
            if job_state.stop_event.is_set():
                raise asyncio.CancelledError()
                
            try:
                # Try to detect either title or description element
                await page.wait_for_selector('h1[data-qa-id="adview_title"], h1, [data-qa-id="adview_description_container"], [data-test-id="description"]', timeout=3000)
                
                # Check for Datadome block page title
                page_title = await page.title()
                if "attention requise" in page_title.lower() or "datadome" in page_title.lower():
                    raise Exception("Blocked by Datadome page title")
                    
                break  # Not blocked, proceed!
            except Exception:
                if not captcha_detected:
                    captcha_detected = True
                    job_state.set_status("captcha_required")
                    job_state.log("⚠️ [BLOCAGE DATADOME DÉTECTÉ SUR L'ANNONCE]")
                    job_state.log(f"👉 Veuillez résoudre le Captcha dans la fenêtre Chromium pour l'annonce : {url}")
                    job_state.log("⏳ Cliquez ensuite sur 'J'ai résolu le Captcha' dans l'interface ou attendez la détection automatique...")
                
                try:
                    await asyncio.wait_for(job_state.captcha_event.wait(), timeout=2.0)
                    job_state.captcha_event.clear()
                    captcha_detected = False
                except asyncio.TimeoutError:
                    pass
        
        if job_state.status == "captcha_required":
            job_state.set_status("scraping")
            job_state.log("✅ Captcha de l'annonce passé !")
            
        await page.wait_for_timeout(1500)
        
        # --- TITLE ---
        title_element = await page.query_selector('h1[data-qa-id="adview_title"], h1')
        title = await title_element.inner_text() if title_element else await page.title()
        
        # --- PRICE ---
        price_element = await page.query_selector('div[data-qa-id="adview_price"], [data-test-id="price"], p[data-qa-id="adview_price"]')
        price_text = await price_element.inner_text() if price_element else "0"
        price = clean_price(price_text)
        
        # --- DESCRIPTION ---
        # Try multiple selectors for the description box
        desc_selectors = [
            'div[data-qa-id="adview_description_container"]',
            '[data-test-id="description"]',
            'div[data-qa-id="adview_description"]',
            'p[data-qa-id="adview_description"]',
        ]
        description = ""
        for sel in desc_selectors:
            desc_element = await page.query_selector(sel)
            if desc_element:
                description = await desc_element.inner_text()
                if description.strip():
                    break
        
        # Fallback 1: meta description
        if not description.strip():
            meta_desc = await page.query_selector('meta[property="og:description"], meta[name="description"]')
            if meta_desc:
                description = await meta_desc.get_attribute('content') or ""
        
        # Fallback 2: extract all visible text from the main content area
        if not description.strip():
            main_content = await page.query_selector('main, article, [role="main"], #app')
            if main_content:
                description = await main_content.inner_text()
            else:
                # Last resort: full body text (truncated)
                description = await page.evaluate('() => document.body.innerText.substring(0, 3000)')
            job_state.log(f"  ℹ️ Description extraite via fallback (texte brut de la page) pour: {title.strip()[:50]}")
        
        # --- ATTRIBUTES (LBC criteria section) ---
        # Gather structured attributes (RAM, CPU, etc.) from the criteria/attributes section
        attributes_text = ""
        attr_elements = await page.query_selector_all('[data-qa-id="criteria_item"], [data-qa-id="adview_criteria"] li, [class*="Attribute"], [class*="criteria"]')
        for attr_el in attr_elements:
            attr_text = await attr_el.inner_text()
            if attr_text.strip():
                attributes_text += attr_text.strip() + " | "
        
        # Combine description with structured attributes for better AI analysis
        full_description = description.strip()
        if attributes_text:
            full_description += f"\n\n[Caractéristiques structurées]: {attributes_text}"

        return {
            "title": title.strip(),
            "price": price,
            "url": url,
            "description": full_description
        }
    except asyncio.CancelledError:
        raise
    except Exception as e:
        job_state.log(f"⚠️ Erreur lors du scraping de {url}: {e}")
        return None

# --- 2. PIPELINE ORCHESTRATION ---
# D-01 : l'analyse IA est entièrement externalisée vers Claude.ai (workflow
# "Générer le prompt + import JSON"). server.py se contente de scraper Leboncoin
# et d'écrire leboncoin_brut.json. Le frontend pilote ensuite l'analyse via Claude.

async def run_pipeline_task(base_url: str, max_pages: int, delay: int = 1500):
    raw_file = "leboncoin_brut.json"
    scraped_ads = []
    
    try:
        job_state.set_status("scraping")
        job_state.log("🚀 Démarrage du pipeline de scraping Leboncoin...")
        
        async with async_playwright() as p:
            job_state.log("🌐 Lancement du navigateur Chromium (mode non-headless)...")
            browser = await p.chromium.launch(
                headless=False, 
                args=['--disable-blink-features=AutomationControlled']
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800}
            )
            page = await context.new_page()

            for page_num in range(1, max_pages + 1):
                if job_state.stop_event.is_set():
                    break

                parsed = urlparse(base_url)
                query = parse_qs(parsed.query)
                query['sort'] = ['time']

                if page_num > 1:
                    query['page'] = [str(page_num)]

                new_query = urlencode(query, doseq=True)
                url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

                job_state.log(f"📄 Scraping de la page de recherche {page_num}/{max_pages}...")
                await page.goto(url, wait_until="domcontentloaded")

                # Datadome check loop
                captcha_detected = False
                while True:
                    if job_state.stop_event.is_set():
                        raise asyncio.CancelledError()

                    try:
                        # Try to detect listing items
                        await page.wait_for_selector('a[data-qa-id="aditem_container"], a[href*="/ad/"]', timeout=3000)
                        break  # Found! Break out of captcha wait
                    except Exception:
                        if not captcha_detected:
                            captcha_detected = True
                            job_state.set_status("captcha_required")
                            job_state.log("⚠️ [BLOCAGE DATADOME DÉTECTÉ OU PAGE LENTE]")
                            job_state.log("👉 Veuillez résoudre le Captcha dans la fenêtre Chromium ouverte.")
                            job_state.log("⏳ Une fois résolu, vous pouvez cliquer sur le bouton 'J'ai résolu le Captcha' dans l'interface ou attendre la détection automatique.")

                        try:
                            # Wait for click on resume OR timeout and loop check again
                            await asyncio.wait_for(job_state.captcha_event.wait(), timeout=2.0)
                            job_state.captcha_event.clear()
                            captcha_detected = False  # Reset flag to re-evaluate selector
                        except asyncio.TimeoutError:
                            pass

                if job_state.status == "captcha_required":
                    job_state.set_status("scraping")
                    job_state.log("✅ Captcha passé ou page chargée avec succès !")

                ad_links_elements = await page.query_selector_all('a[data-qa-id="aditem_container"], a[href*="/ad/"]')
                ad_urls = set()
                for el in ad_links_elements:
                    href = await el.get_attribute('href')
                    if href and '/ad/' in href:
                        full_url = urljoin("https://www.leboncoin.fr", href)
                        ad_urls.add(full_url)

                if not ad_urls:
                    job_state.log("⚠️ Aucune annonce trouvée sur cette page de recherche.")
                    html_content = await page.content()
                    with open("debug_lbc.html", "w", encoding="utf-8") as f:
                        f.write(html_content)
                    job_state.log("HTML de debug enregistré dans 'debug_lbc.html'. Fin de la recherche.")
                    break

                ad_urls = list(ad_urls)
                job_state.log(f"🔎 {len(ad_urls)} annonces trouvées sur la page {page_num}.")

                for idx, ad_url in enumerate(ad_urls):
                    if job_state.stop_event.is_set():
                        break
                    job_state.log(f"  -> [{idx+1}/{len(ad_urls)}] Scraping des détails : {ad_url}")
                    details = await get_ad_details(page, ad_url)
                    if details:
                        scraped_ads.append(details)
                    await page.wait_for_timeout(delay)

            await browser.close()
            
    except asyncio.CancelledError:
        job_state.log("🛑 Job annulé par l'utilisateur.")
        job_state.set_status("idle")
        return
    except Exception as e:
        job_state.log(f"🔴 Erreur pendant le scraping: {e}")
        job_state.set_status("error")
        return

    if job_state.stop_event.is_set():
        job_state.set_status("idle")
        return
        
    # --- SAVE RAW SCRAPED ADS ---
    # D-01 : plus d'analyse Ollama locale. server.py s'arrête après le scrape ;
    # le frontend gère ensuite l'analyse via Claude.ai (workflow "Générer le prompt").
    if not scraped_ads:
        job_state.log("⚠️ Aucune annonce n'a été scrapée.")
        job_state.set_status("idle")
        return

    job_state.log(f"💾 Sauvegarde de {len(scraped_ads)} annonces brutes dans {raw_file}...")
    with open(raw_file, 'w', encoding='utf-8') as f:
        json.dump(scraped_ads, f, ensure_ascii=False, indent=2)

    job_state.results = []  # pas de résultats analysés ; ils arriveront via /api/import-results
    job_state.criteria = criteres  # mémo pour la génération du prompt côté frontend
    job_state.set_status("scraped")
    job_state.broadcast({"type": "scraped", "count": len(scraped_ads)})
    job_state.log(f"🎉 Scraping terminé ! {len(scraped_ads)} annonces prêtes à être analysées via Claude.ai.")


# --- 4. HTTP API ROUTERS ---

async def index_handler(request):
    return web.FileResponse(os.path.join(os.path.dirname(__file__), 'index.html'))

async def style_handler(request):
    return web.FileResponse(os.path.join(os.path.dirname(__file__), 'style.css'))

async def start_handler(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Requête JSON invalide"}, status=400)

    url = data.get("url", "").strip()
    pages = int(data.get("pages", 1))
    criteres = data.get("criteres", "").strip()
    try:
        delay = int(data.get("delay", 1500))
    except (ValueError, TypeError):
        delay = 1500

    if not url:
        return web.json_response({"error": "L'URL est obligatoire."}, status=400)
    if not criteres:
        return web.json_response({"error": "Les critères de recherche sont obligatoires (utilisés ensuite par Claude.ai)."}, status=400)

    if job_state.status in ["scraping", "captcha_required"]:
        return web.json_response({"error": "Un scraping est déjà en cours d'exécution."}, status=400)

    job_state.logs = []
    job_state.results = []
    job_state.total = 0
    job_state.criteria = criteres  # mémorise les critères pour le prompt Claude.ai
    job_state.status = "scraping"
    job_state.captcha_event.clear()
    job_state.stop_event.clear()

    # Run the background task (scrape only — l'analyse se fait ensuite via Claude.ai)
    job_state.task = asyncio.create_task(run_pipeline_task(url, pages, delay))

    return web.json_response({"status": "started"})

async def resume_handler(request):
    if job_state.status == "captcha_required":
        job_state.log("📥 Reprise manuelle signalée par l'utilisateur.")
        job_state.captcha_event.set()
        return web.json_response({"status": "resumed"})
    return web.json_response({"error": "Le scraper n'est pas bloqué par un Captcha."}, status=400)

async def stop_handler(request):
    if job_state.status in ["scraping", "captcha_required"]:
        job_state.log("🛑 Commande d'arrêt reçue de l'utilisateur.")
        job_state.stop_event.set()
        job_state.captcha_event.set()  # Break captcha block if waiting
        if job_state.task:
            job_state.task.cancel()
        job_state.set_status("idle")
        return web.json_response({"status": "stopped"})
    return web.json_response({"error": "Aucun scraper en cours d'exécution."}, status=400)

async def scraped_info_handler(request):
    raw_file = "leboncoin_brut.json"
    if not os.path.exists(raw_file):
        return web.json_response({"available": False, "count": 0})
    try:
        with open(raw_file, 'r', encoding='utf-8') as f:
            ads = json.load(f)
        return web.json_response({"available": True, "count": len(ads)})
    except Exception:
        return web.json_response({"available": False, "count": 0})

async def import_handler(request):
    """Load externally-generated AI results (e.g. from Claude.ai) directly into the app."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "JSON invalide"}, status=400)

    if not isinstance(data, list):
        return web.json_response({"error": "Le corps doit être un tableau JSON d'annonces."}, status=400)

    job_state.results = data
    job_state.set_status("completed")
    job_state.broadcast({"type": "results", "results": data})
    print(f"📥 Import externe : {len(data)} annonces chargées.")
    return web.json_response({"status": "imported", "count": len(data)})

async def raw_ads_handler(request):
    """Sert le fichier leboncoin_brut.json pour que le frontend puisse le télécharger
    (à donner à Claude.ai en pièce jointe). Optionnel — l'utilisateur peut aussi
    récupérer le fichier directement dans son dossier lbc-dealfinder."""
    raw_file = os.path.join(os.path.dirname(__file__), 'leboncoin_brut.json')
    if not os.path.exists(raw_file):
        return web.json_response({"error": "Aucun scraping disponible. Lancez d'abord un scraping."}, status=404)
    return web.FileResponse(raw_file, headers={
        'Content-Disposition': 'attachment; filename="leboncoin_brut.json"'
    })

async def events_handler(request):
    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*'
        }
    )
    await response.prepare(request)
    
    q = asyncio.Queue()
    job_state.clients.add(q)
    
    # Send current state
    try:
        await response.write(f"data: {json.dumps({'type': 'status', 'status': job_state.status})}\n\n".encode('utf-8'))
        # Send historical logs
        for log_msg in job_state.logs:
            await response.write(f"data: {json.dumps({'type': 'log', 'message': log_msg})}\n\n".encode('utf-8'))
        # Si un scraping est terminé (raw ads prêtes) : re-broadcast le scraped event
        if job_state.status == "scraped":
            raw_file = "leboncoin_brut.json"
            count = 0
            if os.path.exists(raw_file):
                try:
                    with open(raw_file, 'r', encoding='utf-8') as f:
                        count = len(json.load(f))
                except Exception:
                    pass
            await response.write(f"data: {json.dumps({'type': 'scraped', 'count': count})}\n\n".encode('utf-8'))
        # Send results if finished (= JSON Claude.ai importé)
        if job_state.status == "completed" and job_state.results:
            await response.write(f"data: {json.dumps({'type': 'results', 'results': job_state.results})}\n\n".encode('utf-8'))
    except (ConnectionResetError, ConnectionError):
        job_state.clients.discard(q)
        return response
        
    try:
        while True:
            data = await q.get()
            await response.write(f"data: {json.dumps(data)}\n\n".encode('utf-8'))
            q.task_done()
    except (asyncio.CancelledError, ConnectionResetError, ConnectionError):
        pass
    finally:
        job_state.clients.discard(q)
        
    return response

# --- CORS / PRIVATE NETWORK ACCESS ---
# Le frontend tourne en HTTPS (GitHub Pages) et appelle ce serveur en HTTP
# sur localhost. Chrome/Edge requièrent ces headers (notamment
# `Access-Control-Allow-Private-Network`) pour autoriser un appel public→privé.

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Allow-Private-Network': 'true',
    'Access-Control-Max-Age': '86400',
}


@web.middleware
async def cors_middleware(request, handler):
    if request.method == 'OPTIONS':
        return web.Response(status=204, headers=CORS_HEADERS)
    response = await handler(request)
    for k, v in CORS_HEADERS.items():
        response.headers[k] = v
    return response


async def options_handler(request):
    return web.Response(status=204, headers=CORS_HEADERS)


async def ping_handler(request):
    """Health-check appelé par le frontend pour détecter le serveur local."""
    return web.json_response({'status': 'ok'})


# --- SERVER BOOT ---

def create_app() -> web.Application:
    """Construit l'app aiohttp. Utilisée par main() et par les tests pytest."""
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get('/', index_handler)
    app.router.add_get('/index.html', index_handler)
    app.router.add_get('/style.css', style_handler)
    # /app.js : ancien fichier supprimé, remplacé par les modules ES6 dans /js/
    # (la route est laissée comme redirection 410 pour debug si un vieux cache navigateur insiste)
    app.router.add_post('/api/start', start_handler)
    app.router.add_post('/api/resume', resume_handler)
    app.router.add_post('/api/stop', stop_handler)
    app.router.add_get('/api/scraped-info', scraped_info_handler)
    app.router.add_get('/api/raw-ads', raw_ads_handler)
    app.router.add_get('/api/events', events_handler)
    app.router.add_post('/api/import-results', import_handler)
    app.router.add_get('/api/ping', ping_handler)
    # Sert tous les modules ES6 sous /js/ uniquement si le dossier existe localement
    # (dev uniquement — en distribution, le frontend est sur GitHub Pages)
    js_path = os.path.join(os.path.dirname(__file__), 'js')
    if os.path.isdir(js_path):
        app.router.add_static('/js/', path=js_path, show_index=False, follow_symlinks=False)
    # Catch-all OPTIONS pour les preflights CORS
    app.router.add_route('OPTIONS', '/{path:.*}', options_handler)
    # SPA fallback : toute route GET non matchée renvoie index.html (le router JS prend le relais)
    app.router.add_get('/{path:.*}', index_handler)
    return app


def main():
    app = create_app()
    print("✨ Le serveur Leboncoin Scraper & IA est lancé !")
    print("👉 Ouvrez votre navigateur sur : http://localhost:8080")
    web.run_app(app, host='localhost', port=8080)

if __name__ == "__main__":
    main()
