import asyncio
import json
import csv
import re
import os
import sys
import statistics
import unicodedata
import aiohttp
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

OLLAMA_API_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5:0.5b"

# --- GLOBAL JOB STATE ---

class ScraperJobState:
    def __init__(self):
        self.status = "idle"  # idle, scraping, captcha_required, analyzing, completed, error
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

# --- 2. IA ANALYSIS UTILS ---

def clean_and_parse_json(raw_text: str) -> dict:
    s = raw_text.strip()
    
    # Remove markdown code fences if present
    if s.startswith("```"):
        lines = s.splitlines()
        if len(lines) >= 2:
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].strip() == "```":
                lines = lines[:-1]
            s = "\n".join(lines).strip()
            
    # Find the JSON object boundaries
    first_brace = s.find("{")
    if first_brace == -1:
        raise ValueError("No JSON object found")
        
    last_brace = s.rfind("}")
    if last_brace != -1 and last_brace > first_brace:
        candidate = s[first_brace:last_brace+1]
    else:
        candidate = s[first_brace:]
        
    # Escape literal control characters inside double quotes
    chars = []
    in_string = False
    escape = False
    for char in candidate:
        if char == '"' and not escape:
            in_string = not in_string
            chars.append(char)
        elif char == '\\' and in_string and not escape:
            escape = True
            chars.append(char)
        else:
            if in_string:
                if char == '\n':
                    chars.append('\\n')
                elif char == '\r':
                    chars.append('\\r')
                elif char == '\t':
                    chars.append('\\t')
                else:
                    chars.append(char)
            else:
                chars.append(char)
            escape = False
            
    cleaned_text = "".join(chars)
    
    # Try parsing the cleaned text directly first
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError:
        pass
        
    # If parsing fails, the JSON might be truncated. Let's try to auto-repair it!
    # If we are inside an unclosed string, close the string first
    repaired_text = cleaned_text
    if in_string:
        repaired_text += '"'
    
    # Try to append closing braces to balance the JSON structure
    for suffix in ["}", '"}', '"]}', '"]"}']:
        try:
            return json.loads(repaired_text + suffix)
        except json.JSONDecodeError:
            pass
            
    # Fallback to regex key-value extraction for highest resilience
    result = {"match_criteres": False}
    
    mc_match = re.search(r'"match_criteres"\s*:\s*(true|false)', cleaned_text, re.IGNORECASE)
    if mc_match:
        result["match_criteres"] = mc_match.group(1).lower() == "true"
        
    nqp_match = re.search(r'"note_qualite_prix"\s*:\s*(\d+(?:[.,]\d+)?)', cleaned_text)
    if nqp_match:
        result["note_qualite_prix"] = float(nqp_match.group(1).replace(',', '.'))
        
    ct_match = re.search(r'"caracteristiques_trouvees"\s*:\s*"([^"]*)"', cleaned_text)
    if ct_match:
        result["caracteristiques_trouvees"] = ct_match.group(1)
    else:
        ct_trunc = re.search(r'"caracteristiques_trouvees"\s*:\s*"([^"]*)$', cleaned_text)
        if ct_trunc:
            result["caracteristiques_trouvees"] = ct_trunc.group(1) + "... (tronqué)"
            
    ec_match = re.search(r'"explication_choix_et_note"\s*:\s*"([^"]*)"', cleaned_text)
    if ec_match:
        result["explication_choix_et_note"] = ec_match.group(1)
    else:
        ec_trunc = re.search(r'"explication_choix_et_note"\s*:\s*"([^"]*)$', cleaned_text)
        if ec_trunc:
            result["explication_choix_et_note"] = ec_trunc.group(1) + "... (tronqué par l'IA)"
            
    if "note_qualite_prix" in result:
        return result
        
    raise ValueError("Could not parse or auto-repair truncated JSON response")

async def analyser_description_ia(session: aiohttp.ClientSession, titre_annonce: str, texte_description: str, prix: float, criteres: str, model: str, contexte_prix: str = "") -> dict:
    bloc_comparaison = ""
    if contexte_prix:
        bloc_comparaison = f"""

POINT DE COMPARAISON — PRIX DU MARCHÉ DANS CE LOT (sers-t'en pour juger si le prix est une bonne affaire ou non) :
{contexte_prix}
"""

    prompt = f"""Tu es un expert intraitable, spécialisé dans l'évaluation d'annonces de seconde main.
Analyse cette annonce selon ces critères précis de recherche : {criteres}.

Le prix affiché par le vendeur est de : {prix} €.{bloc_comparaison}

RÈGLES IMPORTANTES :
⚠️ TU NE REFUSES JAMAIS UNE ANNONCE. Toutes les annonces doivent être notées sans exception. Si une annonce ne correspond pas du tout aux critères, tu ne l'exclus PAS : tu lui attribues simplement une note très basse (proche de 0) et tu expliques pourquoi dans "explication_choix_et_note".
1. CONNAISSANCES SUR LE MODÈLE — TRÈS IMPORTANT : Identifie le modèle ou la référence exacte du produit (ex: "Dell XPS 13 9310", "MacBook Pro 14 M1 Pro", "Lenovo IdeaPad 3 15ITL6", "HP Pavilion 15-eh1xxx"). Si tu reconnais le modèle, tu DOIS compléter toi-même, grâce à tes connaissances d'usine, TOUTES les caractéristiques manquantes de l'annonce (processeur exact, gammes de RAM et de stockage d'origine, type et taille d'écran, carte graphique, année de sortie, etc.). N'écris JAMAIS qu'une info est "manquante", "non précisée", "inconnue" ou "à vérifier" si le modèle permet de la déduire : DÉDUIS-LA. Tu n'as pas accès à internet, mais tu connais les fiches techniques d'usine des modèles courants — utilise-les. Dans "caracteristiques_trouvees", liste à la fois les infos de l'annonce ET celles déduites du modèle (tu peux ajouter "(déduit)" après une caractéristique déduite).
2. NOTE de 0 à 100 (DÉCIMALES AUTORISÉES ET ENCOURAGÉES) évaluant le RAPPORT QUALITÉ/PRIX selon ces sous-critères :
   - Adéquation aux critères demandés (0-35 pts) — C'EST LE PLUS IMPORTANT. Si les caractéristiques ne respectent pas les critères ou sont faibles, la note globale doit rester basse, MÊME si le prix est bas.
   - Prix par rapport au POINT DE COMPARAISON ci-dessus (0-25 pts) : un prix bas n'est une bonne affaire QUE si la qualité/les specs le justifient.
   - État général / vétusté du modèle (0-20 pts)
   - Qualité / complétude de l'annonce (0-20 pts)
   ⚠️ ANTI-BIAIS PRIX BAS : un prix bas ne suffit JAMAIS, à lui seul, à donner une bonne note. Un produit pas cher mais peu performant, ancien ou en mauvais état doit obtenir une note FAIBLE. Juge d'abord la qualité et l'adéquation aux critères ; le prix ne fait que moduler. À l'inverse, un excellent produit à un prix correct (même pas le moins cher) peut obtenir une très bonne note.
   Sois précis, nuancé et sévère. Une note de 90+ est exceptionnelle.
   ⚠️ GRANULARITÉ — UTILISE DES DÉCIMALES : départage les annonces au dixième de point près (ex: 84.5, 87.2, 88.1, 91.7, 93.4). Deux annonces ne doivent quasiment JAMAIS avoir exactement la même note : sers-toi des décimales et du point de comparaison des prix pour les différencier finement. Évite absolument de répéter les mêmes notes rondes (78, 85, 90...).
3. RÈGLES DE VALIDITÉ DU JSON : N'utilise JAMAIS de retours à la ligne réels (touches Entrée) dans tes valeurs de texte (par exemple dans "explication_choix_et_note"). Si tu veux sauter une ligne, écris impérativement la séquence de caractères '\\n' (antislash suivi de n) à la place.

Renvoie UNIQUEMENT un JSON valide respectant exactement ce format (ne renvoie pas d'autres champs que ceux-ci) :
{{"note_qualite_prix": nombre décimal de 0 à 100 avec au moins un chiffre après le point décimal (utilise le POINT, pas la virgule, dans le JSON — ex: 87.4), "caracteristiques_trouvees": "liste très courte des caractéristiques clés identifiées ou déduites du modèle", "explication_choix_et_note": "Justifie ta note (avec ses décimales) et ton choix en détaillant le rapport qualité/prix de cette annonce"}}

Titre de l'annonce :
{titre_annonce}

Description de l'annonce :
{texte_description[:1500]}
"""

    payload = {
        "model": model,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "think": False,  # modèles "thinking" (qwen3.x...) : sinon le JSON part dans 'thinking' et 'response' est vide
        "options": {
            "temperature": 0.35,
            "num_ctx": 4096,
            "num_predict": 1024
        }
    }
    
    try:
        timeout = aiohttp.ClientTimeout(total=120)
        async with session.post(OLLAMA_API_URL, json=payload, timeout=timeout) as response:
            if response.status == 200:
                data = await response.json()
                response_text = data.get("response", "") or ""
                # Filet de sécurité : certains modèles "thinking" laissent 'response' vide
                if not response_text.strip():
                    response_text = (data.get("thinking", "") or "{}")
                try:
                    return clean_and_parse_json(response_text)
                except Exception as e:
                    job_state.log(f"⚠️ Erreur de parsing JSON depuis l'IA : {e} (Réponse brute: {response_text[:300]}...)")
                    return {"match_criteres": False, "explication_choix_et_note": f"Erreur de parsing de la réponse de l'IA (format invalide ou réponse tronquée)"}
            else:
                job_state.log(f"⚠️ Erreur API IA (Status {response.status})")
                return {"match_criteres": False, "explication_choix_et_note": f"Erreur API IA ({response.status})"}
    except Exception as e:
        job_state.log(f"⚠️ Erreur de connexion à l'IA locale: {e}")
        return {"match_criteres": False, "explication_choix_et_note": f"Erreur de connexion IA ({str(e)})"}

# --- 3. PIPELINE ORCHESTRATION ---

def generate_static_html(html_file, annonces_validees, tri):
    if tri == "note":
        stats_text = f"🌟 {len(annonces_validees)} annonces correspondent à vos critères (Triées par les meilleures notes de l'IA)"
    elif tri == "prix":
        stats_text = f"🌟 {len(annonces_validees)} annonces correspondent à vos critères (Triées par prix croissant)"
    else:
        stats_text = f"🌟 {len(annonces_validees)} annonces correspondent à vos critères (Triées par les plus récentes)"
        
    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Résultats IA Leboncoin</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0f172a;
            --card-bg: #1e293b;
            --text: #f8fafc;
            --accent: #3b82f6;
            --accent-hover: #60a5fa;
            --success: #10b981;
            --gold: #fbbf24;
        }}
        body {{
            font-family: 'Inter', system-ui, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 2rem;
            line-height: 1.5;
        }}
        h1 {{ text-align: center; margin-bottom: 0.5rem; background: linear-gradient(to right, #3b82f6, #8b5cf6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2.5rem; }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 1.5rem;
            max-width: 1400px;
            margin: 0 auto;
        }}
        .card {{
            background: var(--card-bg);
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            transition: transform 0.2s, box-shadow 0.2s;
            border: 1px solid #334155;
            display: flex;
            flex-direction: column;
        }}
        .card:hover {{ transform: translateY(-5px); box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2); border-color: var(--accent); }}
        .price {{ font-size: 1.75rem; font-weight: 700; color: var(--success); margin: 0.5rem 0; display: inline-block; }}
        .note-badge {{ float: right; background: rgba(251, 191, 36, 0.2); color: var(--gold); padding: 0.5rem 1rem; border-radius: 8px; font-weight: bold; font-size: 1.2rem; border: 1px solid rgba(251, 191, 36, 0.4); }}
        .title {{ font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem; color: #e2e8f0; line-height: 1.3; clear: both; }}
        .tags {{ display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem; }}
        .tag {{ background: rgba(59, 130, 246, 0.15); color: var(--accent-hover); padding: 0.4rem 0.8rem; border-radius: 8px; font-size: 0.85rem; font-weight: 600; border: 1px solid rgba(59, 130, 246, 0.3); }}
        .explication {{ background: rgba(0,0,0,0.25); padding: 1rem; border-radius: 8px; font-size: 0.9rem; color: #cbd5e1; flex-grow: 1; border-left: 3px solid var(--gold); margin-bottom: 1rem; }}
        .btn {{ display: block; background: var(--accent); color: white; text-decoration: none; padding: 0.75rem 1rem; border-radius: 8px; text-align: center; margin-top: auto; font-weight: 600; transition: background 0.2s, transform 0.1s; }}
        .btn:hover {{ background: var(--accent-hover); transform: scale(1.02); }}
        .stats {{ text-align: center; color: #94a3b8; margin-bottom: 3rem; font-size: 1.1rem; }}
    </style>
</head>
<body>
    <h1>Les Meilleures Affaires Leboncoin</h1>
    <div class="stats">{stats_text}</div>
    <div class="grid">
"""
    
    for a in annonces_validees:
        html_content += f"""
        <div class="card">
            <div>
                <div class="price">{a['prix']} €</div>
                <div class="note-badge">⭐ {a['note_sur_100']}/100</div>
            </div>
            <div class="title">{a['titre']}</div>
            <div class="tags">
                <span class="tag">🔍 {a['caracteristiques']}</span>
            </div>
            <div class="explication">
                <strong>🤖 Analyse Qualité/Prix :</strong><br>
                {a['explication']}
            </div>
            <a href="{a['url']}" target="_blank" class="btn">Voir l'annonce sur Leboncoin</a>
        </div>"""
        
    html_content += """
    </div>
</body>
</html>"""
    
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

def build_price_stats(scraped_ads):
    """Aggregate price statistics over the whole batch to give the AI a comparison anchor."""
    prices = sorted(p for p in (a.get("price", 0) or 0 for a in scraped_ads) if p and p > 0)
    if not prices:
        return None
    return {
        "prices": prices,
        "min": prices[0],
        "max": prices[-1],
        "median": statistics.median(prices),
        "count": len(prices),
    }

def build_price_context(prix, stats):
    """Build a per-listing textual comparison point relative to the batch."""
    if not stats or not prix or prix <= 0:
        return ""
    prices = stats["prices"]
    cheaper_count = sum(1 for p in prices if p > prix)
    pct_cheaper = round(100 * cheaper_count / len(prices))
    return (
        f"- Prix de cette annonce : {prix:.0f} €\n"
        f"- Lot de {stats['count']} annonces comparables : le moins cher = {stats['min']:.0f} €, "
        f"médian = {stats['median']:.0f} €, le plus cher = {stats['max']:.0f} €\n"
        f"- Cette annonce est MOINS CHÈRE que {pct_cheaper}% des annonces du lot."
    )

async def run_pipeline_task(base_url: str, max_pages: int, criteres: str, model: str, tri: str, delay: int = 1500, reuse_scraped: bool = False):
    raw_file = "leboncoin_brut.json"
    result_file = "leboncoin_ia_results.csv"
    scraped_ads = []
    
    try:
        if reuse_scraped and os.path.exists(raw_file):
            job_state.set_status("scraping")
            job_state.log(f"🔄 [RÉ-ANALYSE ACTIVÉE] Chargement des annonces existantes depuis '{raw_file}' (Pas de nouveau scraping)...")
            with open(raw_file, 'r', encoding='utf-8') as f:
                scraped_ads = json.load(f)
            job_state.log(f"📋 {len(scraped_ads)} annonces brutes chargées avec succès !")
        else:
            if reuse_scraped:
                job_state.log(f"⚠️ [RÉ-ANALYSE] Fichier '{raw_file}' introuvable. Lancement du scraping standard...")
                
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
        
    if not reuse_scraped or not os.path.exists(raw_file):
        job_state.log(f"💾 Sauvegarde de {len(scraped_ads)} annonces brutes dans {raw_file}...")
        with open(raw_file, 'w', encoding='utf-8') as f:
            json.dump(scraped_ads, f, ensure_ascii=False, indent=2)

    # --- IA ANALYSIS PHASE ---
    
    if not scraped_ads:
        job_state.log("⚠️ Aucune annonce n'a été scrapée. Fin du traitement.")
        job_state.set_status("completed")
        return
        
    job_state.set_status("analyzing")
    job_state.log(f"🤖 Analyse IA démarrée avec le modèle '{model}'...")

    price_stats = build_price_stats(scraped_ads)
    if price_stats:
        job_state.log(f"📈 Point de comparaison calculé : {price_stats['count']} prix (min {price_stats['min']:.0f}€ / médian {price_stats['median']:.0f}€ / max {price_stats['max']:.0f}€).")

    annonces_validees = []
    job_state.results = annonces_validees  # même référence : se remplit en direct pour les clients SSE
    total_ads = len(scraped_ads)
    job_state.total = total_ads
    try:
        async with aiohttp.ClientSession() as session:
            for idx, ad in enumerate(scraped_ads):
                if job_state.stop_event.is_set():
                    break
                job_state.log(f"🤖 Analyse {idx+1}/{len(scraped_ads)} : {ad['title']} ({ad['price']}€)")

                contexte_prix = build_price_context(ad.get('price', 0), price_stats)
                ia_result = await analyser_description_ia(session, ad['title'], ad['description'], ad['price'], criteres, model, contexte_prix)
                
                note_ia = ia_result.get("note_qualite_prix", 0.0)
                try:
                    note_ia = round(float(str(note_ia).replace(',', '.')), 1)
                except (ValueError, TypeError):
                    note_ia = 0.0
                    
                annonce_finale = {
                    "titre": ad["title"],
                    "prix": ad["price"],
                    "url": ad["url"],
                    "note_sur_100": note_ia,
                    "caracteristiques": ia_result.get("caracteristiques_trouvees", "N/A"),
                    "explication": ia_result.get("explication_choix_et_note", "Pas d'explication fournie"),
                    "match_criteres": True  # plus aucun rejet : toutes les annonces sont notées et gardées
                }
                annonces_validees.append(annonce_finale)

                # Diffusion en direct de la notation qui vient d'être faite
                job_state.broadcast({
                    "type": "result_item",
                    "item": annonce_finale,
                    "index": idx + 1,
                    "total": total_ads
                })

                job_state.log(f"  => ✅ Notée - Note: {note_ia}/100")
                    
    except asyncio.CancelledError:
        job_state.log("🛑 Job annulé par l'utilisateur pendant l'analyse IA.")
        job_state.set_status("idle")
        return
    except Exception as e:
        job_state.log(f"🔴 Erreur durant l'analyse IA: {e}")
        job_state.set_status("error")
        return

    if job_state.stop_event.is_set():
        job_state.set_status("idle")
        return

    # --- SAVE AND REPORT PHASE ---
    
    job_state.log("📊 Tri des résultats et création des rapports...")
    if tri == "note":
        annonces_validees.sort(key=lambda x: x.get("note_sur_100", 0.0), reverse=True)
    elif tri == "prix":
        annonces_validees.sort(key=lambda x: x["prix"])

    if annonces_validees:
        # Save CSV
        keys = annonces_validees[0].keys()
        with open(result_file, 'w', newline='', encoding='utf-8-sig') as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(annonces_validees)
            
        # Save Static HTML Report
        html_file = result_file.replace('.csv', '.html')
        generate_static_html(html_file, annonces_validees, tri)
        job_state.log(f"💾 Fichiers enregistrés : {result_file} et {html_file}")
    else:
        job_state.log("⚠️ Aucune annonce n'a été validée par l'IA.")

    job_state.results = annonces_validees
    job_state.set_status("completed")
    job_state.broadcast({"type": "results", "results": annonces_validees})
    job_state.log(f"🎉 Pipeline complété ! {len(annonces_validees)} annonces retenues.")

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
    tri = data.get("tri", "note")
    model = data.get("model", DEFAULT_MODEL)
    reuse_scraped = bool(data.get("reuseScraped", False))
    try:
        delay = int(data.get("delay", 1500))
    except (ValueError, TypeError):
        delay = 1500
    
    if not url and not reuse_scraped:
        return web.json_response({"error": "L'URL est obligatoire (sauf en mode ré-analyse des annonces déjà scrapées)."}, status=400)
    if reuse_scraped and not os.path.exists("leboncoin_brut.json"):
        return web.json_response({"error": "Aucune annonce déjà scrapée trouvée (leboncoin_brut.json absent). Lancez d'abord un scraping."}, status=400)
    if not criteres:
        return web.json_response({"error": "Les critères de recherche sont obligatoires."}, status=400)
        
    if job_state.status in ["scraping", "captcha_required", "analyzing"]:
        return web.json_response({"error": "Un scraper est déjà en cours d'exécution."}, status=400)
        
    job_state.logs = []
    job_state.results = []
    job_state.total = 0
    job_state.status = "scraping"
    job_state.captcha_event.clear()
    job_state.stop_event.clear()
    
    # Run the background task
    job_state.task = asyncio.create_task(run_pipeline_task(url, pages, criteres, model, tri, delay, reuse_scraped))
    
    return web.json_response({"status": "started"})

async def resume_handler(request):
    if job_state.status == "captcha_required":
        job_state.log("📥 Reprise manuelle signalée par l'utilisateur.")
        job_state.captcha_event.set()
        return web.json_response({"status": "resumed"})
    return web.json_response({"error": "Le scraper n'est pas bloqué par un Captcha."}, status=400)

async def stop_handler(request):
    if job_state.status in ["scraping", "captcha_required", "analyzing"]:
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

async def models_handler(request):
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("http://localhost:11434/api/tags") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m["name"] for m in data.get("models", [])]
                    if models:
                        return web.json_response({"models": models, "fallback": False})
    except Exception as e:
        print(f"⚠️ Impossible de joindre Ollama pour lister les modèles: {e}")
    # Ollama not accessible — signal the frontend with fallback: True (no hardcoded model list)
    return web.json_response({"models": [], "fallback": True})

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
        # Rejoue les notations déjà faites si une analyse est en cours (reconnexion / rechargement)
        if job_state.status == "analyzing" and job_state.results:
            total_ads = job_state.total or len(job_state.results)
            for i, item in enumerate(list(job_state.results)):
                await response.write(f"data: {json.dumps({'type': 'result_item', 'item': item, 'index': i + 1, 'total': total_ads})}\n\n".encode('utf-8'))
        # Send results if finished
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
    app.router.add_get('/api/models', models_handler)
    app.router.add_get('/api/scraped-info', scraped_info_handler)
    app.router.add_get('/api/events', events_handler)
    app.router.add_post('/api/import-results', import_handler)
    app.router.add_get('/api/ping', ping_handler)
    # Sert tous les modules ES6 sous /js/ (main.js, router.js, pages/, etc.)
    app.router.add_static('/js/', path=os.path.join(os.path.dirname(__file__), 'js'),
                          show_index=False, follow_symlinks=False)
    # Catch-all OPTIONS pour les preflights CORS
    app.router.add_route('OPTIONS', '/{path:.*}', options_handler)
    return app


def main():
    app = create_app()
    print("✨ Le serveur Leboncoin Scraper & IA est lancé !")
    print("👉 Ouvrez votre navigateur sur : http://localhost:8080")
    web.run_app(app, host='localhost', port=8080)

if __name__ == "__main__":
    main()
