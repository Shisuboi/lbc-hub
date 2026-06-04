# Notifications Telegram — Design Spec

**Date :** 2026-06-04
**Statut :** validé

## Contexte

Le moteur tourne 24/7 et publie des opportunités 🔴 urgentes dans Supabase. Personne n'est
devant l'écran — les membres doivent être alertés en temps réel sur Telegram. Les alertes
techniques (captcha Datadome) permettent à Tristan d'intervenir sans surveiller les logs.

## Objectif

- **Opportunités 🔴** → notification dans le groupe Telegram partagé (1 message par opp, sans doublon)
- **Captcha Datadome** → DM Tristan uniquement (le scraping est bloqué, intervention requise)

## Décisions de design

| Question | Décision |
|---|---|
| Déclencheur opportunités | `category == "urgent"` uniquement |
| Destination opportunités | Groupe Telegram (TELEGRAM_GROUP_ID) |
| Destination alertes captcha | DM Tristan (TELEGRAM_TRISTAN_ID) |
| Dédup | Table `telegram_sent` dans Brain SQLite (ad_id) |
| Silence sans config | Si `TELEGRAM_BOT_TOKEN` absent → mode silencieux, zéro impact |
| Best-effort | Toute erreur Telegram est loguée, jamais bloquante |

## Architecture

```
engine/telegram.py    → TelegramClient + send_opportunity + send_alert
engine/db.py          → table telegram_sent + is_telegram_sent + mark_telegram_sent
engine/enrich.py      → hook après insert 🔴 (si non déjà envoyé)
engine/bootstrap.py   → hook détection captcha (après premier timeout ready_selector)
server.py             → crée TelegramClient si token présent, injecte dans workers
```

## Module `engine/telegram.py`

```python
class TelegramClient:
    def __init__(self, token: str, group_id: str, tristan_id: str, session: aiohttp.ClientSession):
        ...
```

Deux fonctions publiques (best-effort — absorbent toute exception) :

### `send_opportunity(client, opp: dict) -> None`

Envoie au groupe (`client.group_id`) un message Markdown :

```
🔴 *<titre>*

💰 Prix : <prix> €
📈 Marge estimée : +<marge_eur> €
📍 <location_city>

🔗 [Voir sur LBC](<url>)
🏠 [Voir sur le hub](https://shisuboi.github.io/lbc-hub/item/<id>)
```

Champs optionnels : `location_city` omis si null ; `est_margin_eur` omis si null ou ≤ 0.

### `send_alert(client, text: str) -> None`

Envoie au DM Tristan (`client.tristan_id`) un message texte brut.

### Appel API

`POST https://api.telegram.org/bot{token}/sendMessage`
```json
{"chat_id": "...", "text": "...", "parse_mode": "Markdown"}
```

Timeout 10s. En cas d'erreur : `print(f"[telegram] erreur envoi : {exc}")`, retour silencieux.

## Brain SQLite — `telegram_sent`

Ajout dans `SCHEMA` de `engine/db.py` :

```sql
CREATE TABLE IF NOT EXISTS telegram_sent (
    ad_id TEXT PRIMARY KEY,
    sent_at INTEGER NOT NULL
);
```

Nouvelles méthodes sur `Brain` :

```python
def is_telegram_sent(self, ad_id: str) -> bool:
    """True si une notif Telegram a déjà été envoyée pour cet ad_id."""

def mark_telegram_sent(self, ad_id: str, now: int | None = None) -> None:
    """Enregistre qu'une notif Telegram a été envoyée pour cet ad_id."""
```

## Hook `engine/enrich.py`

`enrich_once` reçoit un nouveau paramètre optionnel `telegram=None`.

Après l'insert final de l'opportunité (ligne ~115, après vérif/photo) :

```python
if telegram and payload.get("category") == "urgent":
    ad_id = payload.get("ad_id", "")
    if ad_id and not brain.is_telegram_sent(ad_id):
        await send_opportunity(telegram, payload)
        brain.mark_telegram_sent(ad_id)
```

L'`enrichment_worker` passe `telegram` à `enrich_once`.

## Hook `engine/bootstrap.py`

`make_scrape_fn` reçoit un nouveau paramètre optionnel `telegram=None`.

Au moment du blocage captcha (après le premier timeout `ready_timeout_ms`, avant l'attente longue) :

```python
if telegram:
    await send_alert(telegram, "⚠️ Captcha Datadome détecté — scraping bloqué. Résous-le dans la fenêtre Chromium.")
```

## Configuration `server.py`

```python
# Telegram (optionnel)
telegram = None
if cfg.get("TELEGRAM_BOT_TOKEN") and cfg.get("TELEGRAM_GROUP_ID") and cfg.get("TELEGRAM_TRISTAN_ID"):
    telegram = TelegramClient(
        cfg["TELEGRAM_BOT_TOKEN"],
        cfg["TELEGRAM_GROUP_ID"],
        cfg["TELEGRAM_TRISTAN_ID"],
        session,
    )
    print("📨 Notifications Telegram activées.")
else:
    print("📨 Telegram non configuré — notifications désactivées.")
```

`telegram` est passé à :
- `enrichment_worker(…, telegram=telegram)`
- `make_scrape_fn(…, telegram=telegram)`

## `.env.example`

```
# TELEGRAM_BOT_TOKEN=...         # Token du bot (@BotFather)
# TELEGRAM_GROUP_ID=...          # chat_id du groupe partagé (ex. -1001234567890)
# TELEGRAM_TRISTAN_ID=...        # chat_id DM Tristan (ex. 123456789)
```

## Tests

| Fichier | Tests |
|---|---|
| `tests/test_engine_telegram.py` | `send_opportunity` : message bien formé (avec/sans ville, sans marge) ; `send_alert` : DM Tristan ; erreur HTTP → pas d'exception levée |
| `tests/test_engine_db_telegram.py` | `is_telegram_sent` absent → False ; `mark_telegram_sent` puis `is_telegram_sent` → True ; idempotent |
| `tests/test_engine_enrich.py` | Ajout : opportunité 🔴 → `send_opportunity` appelée + marquée ; 2ᵉ passage même ad_id → pas de 2ᵉ envoi |

## Fichiers modifiés / créés

| Fichier | Action |
|---|---|
| `engine/telegram.py` | Créer |
| `engine/db.py` | Modifier (SCHEMA + 2 méthodes) |
| `engine/enrich.py` | Modifier (paramètre `telegram` + hook) |
| `engine/bootstrap.py` | Modifier (paramètre `telegram` + hook captcha) |
| `server.py` | Modifier (création TelegramClient + injection) |
| `.env.example` | Modifier (3 variables Telegram commentées) |
| `tests/test_engine_telegram.py` | Créer |
| `tests/test_engine_db_telegram.py` | Créer |

## Hors scope

- Alertes démarrage/arrêt moteur (décision B — captcha uniquement)
- Préférences par membre (`member_settings`)
- Relance 24h (dépend du Journal trading, feature suivante)
- Les notifs 🔴 resteront silencieuses tant que Pro Gemini n'est pas activé (gate existant)
