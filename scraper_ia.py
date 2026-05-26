import asyncio
import json
import csv
import re
import argparse
import unicodedata
import aiohttp
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from playwright.async_api import async_playwright

OLLAMA_API_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5:0.5b" 

# --- 1. SCRAPING (Playwright) ---

async def get_ad_details(page, url):
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000) 
        
        title_element = await page.query_selector('h1[data-qa-id="adview_title"], h1')
        title = await title_element.inner_text() if title_element else await page.title()
        
        price_element = await page.query_selector('div[data-qa-id="adview_price"], [data-test-id="price"]')
        price_text = await price_element.inner_text() if price_element else "0"
        
        desc_element = await page.query_selector('div[data-qa-id="adview_description_container"], [data-test-id="description"]')
        if desc_element:
            description = await desc_element.inner_text()
        else:
            meta_desc = await page.query_selector('meta[property="og:description"], meta[name="description"]')
            description = await meta_desc.get_attribute('content') if meta_desc else ""
        
        # Parse price with Unicode-safe cleaning (handles French narrow no-break spaces)
        cleaned_price = unicodedata.normalize('NFKD', price_text)
        cleaned_price = re.sub(r'[^\d.,]', '', cleaned_price)
        cleaned_price = cleaned_price.replace(',', '.')
        try:
            price = float(cleaned_price) if cleaned_price else 0.0
        except ValueError:
            price = 0.0

        return {
            "title": title.strip(),
            "price": price,
            "url": url,
            "description": description.strip()
        }
    except Exception as e:
        print(f"Erreur lors du scraping de {url}: {e}")
        return None

async def scrape_leboncoin(base_url: str, max_pages: int, output_json: str, delay: int = 1500):
    print(f"Démarrage du scraping sur {max_pages} page(s)...")
    results = []
    
    async with async_playwright() as p:
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
            parsed = urlparse(base_url)
            query = parse_qs(parsed.query)
            
            query['sort'] = ['time']
            
            if page_num > 1:
                query['page'] = [str(page_num)]
                
            new_query = urlencode(query, doseq=True)
            url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
                
            print(f"Scraping de la page de recherche {page_num}: {url}")
            
            await page.goto(url, wait_until="domcontentloaded")
            
            try:
                await page.wait_for_selector('a[data-qa-id="aditem_container"], a[href*="/ad/"]', timeout=5000)
            except:
                print("\n⚠️ [BLOCAGE DATADOME DÉTECTÉ OU PAGE LENTE]")
                print("👉 Allez sur la fenêtre du navigateur qui est ouverte et résolvez manuellement le Captcha.")
                print("⏳ Une fois que vous voyez les annonces s'afficher correctement, retournez ici et appuyez sur la touche ENTRÉE pour continuer le script...")
                await asyncio.get_event_loop().run_in_executor(None, input)
                await page.wait_for_timeout(2000)
            
            ad_links_elements = await page.query_selector_all('a[data-qa-id="aditem_container"], a[href*="/ad/"]')
            
            ad_urls = set()
            for el in ad_links_elements:
                href = await el.get_attribute('href')
                if href and '/ad/' in href:
                    full_url = urljoin("https://www.leboncoin.fr", href)
                    ad_urls.add(full_url)
            
            if not ad_urls:
                print("Aucune annonce trouvée même après vérification. Fin du scraping.")
                html_content = await page.content()
                with open("debug_lbc.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                print("⚠️ Code HTML de la page sauvegardé dans 'debug_lbc.html' pour inspection.")
                break
                
            ad_urls = list(ad_urls)
            print(f"{len(ad_urls)} annonces trouvées sur la page {page_num}.")
            
            for ad_url in ad_urls:
                print(f"  -> Extraction : {ad_url}")
                details = await get_ad_details(page, ad_url)
                if details:
                    results.append(details)
                await page.wait_for_timeout(delay)

        await browser.close()
        
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Scraping terminé. {len(results)} annonces sauvegardées dans {output_json}")


# --- 2. EXTRACTION IA LOCALE ---

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
        
    nqp_match = re.search(r'"note_qualite_prix"\s*:\s*(\d+)', cleaned_text)
    if nqp_match:
        result["note_qualite_prix"] = int(nqp_match.group(1))
        
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

async def analyser_description_ia(session: aiohttp.ClientSession, titre_annonce: str, texte_description: str, prix: float, criteres: str, model: str = DEFAULT_MODEL) -> dict:
    prompt = f"""Tu es un expert intraitable, spécialisé dans l'évaluation d'annonces de seconde main.
Analyse cette annonce selon ces critères précis de recherche : {criteres}.

Le prix affiché par le vendeur est de : {prix} €.

RÈGLES IMPORTANTES :
1. Si le modèle exact du produit est mentionné, UTILISE TES CONNAISSANCES PERSONNELLES (tu n'as pas accès à internet en direct) pour déduire ses caractéristiques techniques d'usine si elles manquent dans l'annonce.
2. Attribue une note PRECISE de 0 à 100 qui évalue strictement le RAPPORT QUALITÉ/PRIX en suivant ces sous-critères :
   - Adéquation aux critères demandés (0-30 pts)
   - Prix compétitif par rapport au marché de l'occasion (0-30 pts)
   - État général / vétusté du modèle (0-20 pts)
   - Qualité / complétude de l'annonce (0-20 pts)
   Sois précis et sévère. Ne donne PAS de note ronde systématiquement. Une note de 90+ est une affaire exceptionnelle.
3. RÈGLES DE VALIDITÉ DU JSON : N'utilise JAMAIS de retours à la ligne réels (touches Entrée) dans tes valeurs de texte (par exemple dans "explication_choix_et_note"). Si tu veux sauter une ligne, écris impérativement la séquence de caractères '\\n' (antislash suivi de n) à la place.

Renvoie UNIQUEMENT un JSON valide respectant exactement ce format (ne renvoie pas d'autres champs que ceux-ci) :
{{"match_criteres": booléen (true si ça correspond aux besoins, false sinon), "note_qualite_prix": nombre entier de 0 à 100 (ex: 67), "caracteristiques_trouvees": "liste très courte des caractéristiques clés identifiées ou déduites", "explication_choix_et_note": "Justifie ta note sur 100 et ton choix en détaillant le rapport qualité/prix de cette annonce"}}

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
        "options": {
            "temperature": 0.1,
            "num_ctx": 4096,
            "num_predict": 1024
        }
    }
    
    try:
        async with session.post(OLLAMA_API_URL, json=payload) as response:
            if response.status == 200:
                data = await response.json()
                response_text = data.get("response", "{}")
                try:
                    return clean_and_parse_json(response_text)
                except Exception as e:
                    print(f"Erreur de parsing JSON depuis l'IA : {e} (Réponse brute: {response_text[:300]}...)")
                    return {"match_criteres": False, "explication_choix_et_note": "Erreur de format de réponse de l'IA (réponse tronquée ou malformée)"}
            else:
                print(f"Erreur API IA (Status {response.status})")
                return {"match_criteres": False}
    except Exception as e:
        print(f"Erreur de connexion à l'IA locale: {e}")
        return {"match_criteres": False}

async def process_ai_analysis(input_json: str, output_csv: str, criteres: str, model: str, tri: str):
    print(f"\nDémarrage de l'analyse IA (Modèle : {model})...")
    
    try:
        with open(input_json, 'r', encoding='utf-8') as f:
            annonces = json.load(f)
    except FileNotFoundError:
        print(f"Fichier {input_json} introuvable. Veuillez d'abord scraper les annonces.")
        return

    annonces_validees = []
    
    async with aiohttp.ClientSession() as session:
        for i, annonce in enumerate(annonces):
            print(f"Analyse {i+1}/{len(annonces)} : {annonce['title']} ({annonce['price']}€)")
            
            ia_result = await analyser_description_ia(session, annonce['title'], annonce['description'], annonce['price'], criteres, model)
            
            if ia_result.get("match_criteres") is True:
                # Récupération de la note sécurisée
                note_ia = ia_result.get("note_qualite_prix", 0)
                try:
                    note_ia = float(note_ia)
                except:
                    note_ia = 0.0
                    
                annonce_finale = {
                    "titre": annonce["title"],
                    "prix": annonce["price"],
                    "url": annonce["url"],
                    "note_sur_100": note_ia,
                    "caracteristiques": ia_result.get("caracteristiques_trouvees", "N/A"),
                    "explication": ia_result.get("explication_choix_et_note", "Pas d'explication fournie")
                }
                annonces_validees.append(annonce_finale)
                print(f"  => [V] Gardée - Note: {note_ia}/10")
            else:
                print(f"  => [X] Rejetée : {ia_result.get('explication_choix_et_note', 'Ne correspond pas aux critères')}")

    # Logique de tri
    if tri == "note":
        annonces_validees.sort(key=lambda x: x.get("note_sur_100", 0), reverse=True)
        stats_text = f"🌟 {len(annonces_validees)} annonces correspondent à vos critères (Triées par les meilleures notes de l'IA)"
    elif tri == "prix":
        annonces_validees.sort(key=lambda x: x["prix"])
        stats_text = f"🌟 {len(annonces_validees)} annonces correspondent à vos critères (Triées par prix croissant)"
    else:
        stats_text = f"🌟 {len(annonces_validees)} annonces correspondent à vos critères (Triées par les plus récentes)"
    
    if not annonces_validees:
        print("\nAucune annonce ne correspond à vos critères après analyse IA.")
        return
        
    keys = annonces_validees[0].keys()
    with open(output_csv, 'w', newline='', encoding='utf-8-sig') as f:
        dict_writer = csv.DictWriter(f, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(annonces_validees)
        
    # Génération d'un fichier HTML esthétique et interactif
    html_file = output_csv.replace('.csv', '.html')
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

    print(f"\nTerminé ! {len(annonces_validees)} annonces validées et triées.")
    print(f"📄 Fichier CSV sauvegardé : {output_csv}")
    print(f"🎨 Tableau de bord HTML généré : {html_file}")

# --- MAIN CONTROLLER ---

def main():
    parser = argparse.ArgumentParser(description="Pipeline : Scraper Leboncoin + Extraction IA Locale")
    parser.add_argument("--action", choices=["scrape", "analyze", "both"], default="both", 
                        help="Action à effectuer (par défaut 'both').")
    parser.add_argument("--url", type=str, default="https://www.leboncoin.fr/recherche?category=9&text=pc%20portable",
                        help="URL de recherche Leboncoin exacte.")
    parser.add_argument("--pages", type=int, default=1, help="Nombre de pages de résultats à scraper")
    parser.add_argument("--criteres", type=str, default="Trouve l'objet de mon choix",
                        help="Critères d'extraction et de validation pour l'IA")
    parser.add_argument("--tri", choices=["note", "prix", "recent"], default="note", 
                        help="Mode de tri des résultats (Par défaut: 'note' des meilleures affaires)")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Nom du modèle Ollama à interroger")
    parser.add_argument("--delay", type=int, default=1500, help="Délai entre chaque annonce en millisecondes")
    
    args = parser.parse_args()
    
    raw_file = "leboncoin_brut.json"
    result_file = "leboncoin_ia_results.csv"
    
    if args.action in ["scrape", "both"]:
        asyncio.run(scrape_leboncoin(args.url, args.pages, raw_file, args.delay))
        
    if args.action in ["analyze", "both"]:
        asyncio.run(process_ai_analysis(raw_file, result_file, args.criteres, args.model, args.tri))

if __name__ == "__main__":
    main()
