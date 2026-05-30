# TESTING — Phase B (validation LIVE, obligatoire avant « fini »)

> Leçon de la Phase A : les fixtures ne suffisent pas. On valide contre la **vraie API Gemini**
> et de **vraies opportunités** avant de déclarer la Phase B terminée.

## Pré-requis

1. Une clé `GEMINI_API_KEY` (free tier, [Google AI Studio](https://aistudio.google.com/)) dans `.env`.
   Laisser `GEMINI_PRO_ENABLED=false` (Pro suspendu — cf. `MIN_TIER_FOR_URGENT=pro`).
2. Au moins une `watchlist_searches` active avec une vraie URL LBC (triée par date).
3. Suite verte : `python -m pytest tests/ -v` → tout passe (62 Phase A + Phase B).

## Procédure

1. Lancer le moteur : `python server.py --auto`.
   - Vérifier au démarrage le log `🧠 Worker d'enrichissement IA démarré (cascade).`
     (si `⚠️ Pas de GEMINI_API_KEY` apparaît → la clé n'est pas chargée).
2. Observer les logs : scrape → mise en file → triage groupé → écriture.
3. Dans Supabase, table `opportunities`, vérifier sur les nouvelles lignes :
   - `category` ∈ {`interesting`, `passable`} — **JAMAIS `urgent`** tant que Pro est off.
   - `resale_score` non-null.
   - Pour les candidates (creusées) : `est_market_price`, `est_margin_eur`, `est_margin_pct`,
     `max_buy_price`, `explanation` renseignés.
4. **Aucune ligne brute** (`category` null) ne doit apparaître côté Supabase.
5. Grounding : la table SQLite `market_observations` (cerveau `lbc_brain.sqlite3`) se remplit.
6. Quotas : la table SQLite `llm_usage` s'incrémente ; **aucune erreur 429 silencieuse** dans les logs.
7. Résilience réseau : couper Internet ~1 min en plein cycle → les annonces restent en file
   (`pending_enrichment`) / outbox, **rien n'est perdu**, l'écriture reprend au retour.
8. Robustesse : laisser tourner plusieurs cycles → la file `pending_enrichment` ne gonfle pas
   indéfiniment (les items sont consommés ou abandonnés après 5 échecs).

## Quand le Pro sera disponible (plus tard)

1. Dans `.env` : `GEMINI_PRO_ENABLED=true`, `GEMINI_VERIFY_MODEL=gemini-3.1-pro-preview`,
   et `GEMINI_API_KEY` = clé du compte qui détient les crédits Cloud / l'abo Pro.
2. Relancer `python server.py --auto`.
3. Vérifier que des `category = urgent` (🔴) apparaissent enfin — et **seulement** quand
   le score ET la marge dépassent les seuils (`min_margin_eur` / `min_margin_pct` de la
   recherche, défaut 30 € ET 30 %, score ≥ `URGENT_SCORE_THRESHOLD`, défaut 75).
4. Vérifier qu'un `scam_risk` élevé à la photo **rétrograde** bien un 🔴 en 🟡.

## Réglages utiles (`.env`)

| Clé | Défaut | Rôle |
|---|---|---|
| `GEMINI_API_KEY` | (absente) | Sans elle, enrichissement désactivé |
| `GEMINI_PRO_ENABLED` | `false` | `true` = active le Pro comme vérificateur 🔴 |
| `GEMINI_VERIFY_MODEL` | `gemini-3.1-flash-lite` | Modèle de vérification (mettre le Pro une fois activé) |
| `MIN_TIER_FOR_URGENT` | `pro` | Tier minimum pour déclarer 🔴 |
| `URGENT_SCORE_THRESHOLD` | `75` | Score mini pour un 🔴 |
| `DEFAULT_MIN_MARGIN_EUR` | `30` | Marge € mini si non réglée par recherche |
| `DEFAULT_MIN_MARGIN_PCT` | `30` | Marge % mini si non réglée par recherche |
