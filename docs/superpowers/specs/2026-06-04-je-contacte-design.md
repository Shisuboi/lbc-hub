# « Je contacte » — Signal de coordination — Design Spec

**Date :** 2026-06-04
**Statut :** validé

## Contexte

Quand une opportunité 🔴 arrive, les membres doivent pouvoir se coordonner rapidement pour
éviter que deux personnes contactent le même vendeur. Le signal « Je contacte » s'intègre
dans le fil de commentaires existant (`item_comments`) sans créer de nouveau système.

La nouveauté clé : ce signal peut être déclenché directement depuis le **message Telegram** du
groupe, d'une simple pression sur le téléphone, sans ouvrir le hub.

## Décisions de design

| Question | Décision |
|---|---|
| Affichage | Commentaire spécial pinné en haut du fil, visuellement distinct |
| Stockage | Colonne `type` + `cancelled_at` sur `item_comments` |
| Exclusivité | Un seul signal actif par opportunité (index unique partiel) |
| Annulation | Auteur ou admin uniquement |
| Bouton Telegram | Inline keyboard `🤝 Je m'en occupe` dans le message 🔴 |
| Identité Telegram | `{first_name} (via Telegram)` — pas de mapping profil hub |

## Architecture

```
Frontend /item/:id
  → RPC create_contact_signal(opportunity_id)   ← SDK JS
  → RPC cancel_contact_signal(comment_id)       ← SDK JS

Bot Telegram (callback_query "contact:{opportunity_id}")
  → engine/telegram_bot.py telegram_poll_worker ← coroutine moteur
  → Supa.create_contact_from_telegram()         ← service_role, bypass RLS
  → TelegramClient.answer_callback()            ← toast confirmation

Feed /feed
  → loadCommentMeta exclut type='contact' du count (pas des signaux dans les badges)
```

## Migration SQL (`supabase/migrations/2026-06-04-je-contacte.sql`)

```sql
-- 1. Étendre item_comments
ALTER TABLE item_comments
  ADD COLUMN IF NOT EXISTS type TEXT NOT NULL DEFAULT 'comment',
  ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;

-- 2. Contrainte : un seul signal actif par opportunité (DB-level)
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_contact
  ON item_comments(opportunity_id)
  WHERE type = 'contact' AND cancelled_at IS NULL;

-- 3. RPC create_contact_signal (utilisateur authentifié → hub)
CREATE OR REPLACE FUNCTION create_contact_signal(p_opportunity_id UUID)
RETURNS SETOF item_comments
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE v_username TEXT;
BEGIN
  SELECT username INTO v_username FROM profiles WHERE id = auth.uid();
  IF v_username IS NULL THEN
    RAISE EXCEPTION 'Profil introuvable.';
  END IF;
  RETURN QUERY
    INSERT INTO item_comments(opportunity_id, user_id, body, type)
    VALUES (
      p_opportunity_id,
      auth.uid(),
      '🤝 ' || v_username || ' s''en occupe',
      'contact'
    )
    RETURNING *;
END;
$$;

-- 4. RPC cancel_contact_signal (auteur ou admin)
CREATE OR REPLACE FUNCTION cancel_contact_signal(p_comment_id UUID)
RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM item_comments ic
    WHERE ic.id = p_comment_id
    AND (
      ic.user_id = auth.uid()
      OR EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin')
    )
  ) THEN
    RAISE EXCEPTION 'Accès refusé.';
  END IF;
  UPDATE item_comments SET cancelled_at = now() WHERE id = p_comment_id;
END;
$$;
```

> L'index unique `uq_active_contact` garantit l'exclusivité au niveau base (erreur 23505 si
> un second signal actif tente d'être inséré). Les RPCs gèrent ce cas gracieusement.

## Frontend — `js/lib/comments.js`

### SELECT étendu

Ajouter `type, cancelled_at` :

```javascript
const SELECT = 'id, opportunity_id, user_id, body, edited_at, created_at, type, cancelled_at, author:profiles(username, avatar_color)';
```

### Nouvelles fonctions

```javascript
/** Crée un signal de contact via RPC (retourne le commentaire créé). */
export async function createContactSignal(opportunityId) {
  const { data, error } = await supa.rpc('create_contact_signal', { p_opportunity_id: opportunityId });
  if (error) throw new Error(error.message);
  return data;
}

/** Annule un signal de contact via RPC. */
export async function cancelContactSignal(commentId) {
  const { error } = await supa.rpc('cancel_contact_signal', { p_comment_id: commentId });
  if (error) throw new Error(error.message);
}
```

### `loadCommentMeta` — exclure les contacts du count

```javascript
// Dans la boucle de loadCommentMeta, ignorer les signaux de contact :
if (row.type === 'contact') continue;
```

## Frontend — `js/components/comments.js`

### Rendu du signal de contact (pinned)

Dans `rowHtml`, détecter `c.type === 'contact'` :
- Si `cancelled_at` non null → ne pas afficher (signal annulé)
- Si actif → afficher en haut avec classe `cm-contact-pin` :

```html
<div class="cm-contact-pin" data-id="${c.id}">
  <span class="cm-contact-icon">🤝</span>
  <div class="cm-body">
    <span class="cm-contact-text">${esc(c.body)}</span>
    <span class="cm-time">${timeAgo(c.created_at)}</span>
  </div>
  ${(c.user_id === me?.id || isAdmin)
    ? `<button class="cm-link cm-cancel-contact" data-cancel-contact="${c.id}">✋ Annuler</button>`
    : ''}
</div>
```

### Bouton « Je contacte »

En bas du fil (avant le form), visible/grisé selon l'état actif :

```javascript
const activeContact = comments.find(c => c.type === 'contact' && !c.cancelled_at);
const contactBtnHtml = activeContact
  ? `<div class="cm-contact-taken">🤝 ${esc(activeContact.body)} · déjà pris</div>`
  : `<button id="cmContactBtn" class="btn-contact">🤝 Je contacte cette annonce</button>`;
```

### Gestion des clics (annulation + création)

```javascript
// Annulation
listEl.addEventListener('click', async e => {
  const cancelBtn = e.target.closest('[data-cancel-contact]');
  if (cancelBtn) {
    await cancelContactSignal(cancelBtn.dataset.cancelContact);
    await reload();
  }
});

// Création
container.addEventListener('click', async e => {
  if (e.target.id === 'cmContactBtn') {
    try { await createContactSignal(opportunityId); await reload(); }
    catch (err) { alert(err.message); }
  }
});
```

### `renderList` — trier : contact actif d'abord

```javascript
function renderList() {
  const contact = comments.find(c => c.type === 'contact' && !c.cancelled_at);
  const regular = comments.filter(c => c.type === 'comment' || c.cancelled_at);
  const ordered = contact ? [contact, ...regular] : regular;
  // render ordered...
}
```

## CSS (`style.css`)

```css
/* ===== Signal « Je contacte » ===== */
.cm-contact-pin {
  display: flex; align-items: center; gap: 10px;
  background: rgba(99,102,241,.15); border: 1px solid rgba(99,102,241,.3);
  border-radius: 10px; padding: 10px 14px; margin-bottom: 10px;
}
.cm-contact-icon { font-size: 1.3rem; }
.cm-contact-text { font-weight: 600; }
.cm-cancel-contact { margin-left: auto; opacity: .5; font-size: .8rem; }
.cm-contact-taken {
  text-align: center; opacity: .45; font-size: .85rem; padding: 8px;
  background: rgba(255,255,255,.04); border-radius: 8px; margin-top: 8px;
}
.btn-contact {
  width: 100%; margin-top: 8px; padding: 9px; border-radius: 8px; font-size: .9rem;
  background: rgba(99,102,241,.25); border: 1px solid rgba(99,102,241,.35);
  color: inherit; cursor: pointer; transition: background .15s;
}
.btn-contact:hover { background: rgba(99,102,241,.4); }
```

## Telegram — bouton inline dans les messages 🔴

### `engine/telegram.py` — `send_opportunity` étendu

Ajouter `reply_markup` avec le bouton inline :

```python
import json as _json

async def send_opportunity(client: TelegramClient, opp: dict) -> None:
    opp_id = opp.get("id") or opp.get("ad_id", "")
    reply_markup = _json.dumps({
        "inline_keyboard": [[{
            "text": "🤝 Je m'en occupe",
            "callback_data": f"contact:{opp_id}"
        }]]
    }) if opp_id else None

    body = {"chat_id": client.group_id, "text": _format_opportunity(opp), "parse_mode": "Markdown"}
    if reply_markup:
        body["reply_markup"] = reply_markup
    # ... reste inchangé
```

### `engine/db.py` — offset de polling Telegram

Nouvelle table dans `SCHEMA` :

```sql
CREATE TABLE IF NOT EXISTS telegram_poll_offset (
    id INTEGER PRIMARY KEY DEFAULT 1,
    offset INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO telegram_poll_offset (id, offset) VALUES (1, 0);
```

Nouvelles méthodes :

```python
def get_telegram_offset(self) -> int:
    row = self.conn.execute("SELECT offset FROM telegram_poll_offset WHERE id = 1").fetchone()
    return row["offset"] if row else 0

def set_telegram_offset(self, offset: int) -> None:
    self.conn.execute(
        "INSERT INTO telegram_poll_offset(id, offset) VALUES(1,?) "
        "ON CONFLICT(id) DO UPDATE SET offset=excluded.offset", (offset,)
    )
    self.conn.commit()
```

### `engine/telegram.py` — `TelegramClient` étendu

Nouvelles méthodes :

```python
async def get_updates(self, offset: int = 0) -> list[dict]:
    """Récupère les updates depuis l'offset (long-poll 5s). Best-effort."""
    try:
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        async with self.session.post(
            url, json={"offset": offset, "timeout": 5, "allowed_updates": ["callback_query"]},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            return data.get("result", [])
    except Exception:
        return []

async def answer_callback(self, callback_query_id: str, text: str) -> None:
    """Répond à un callback_query (toast Telegram). Best-effort."""
    try:
        url = f"https://api.telegram.org/bot{self.token}/answerCallbackQuery"
        async with self.session.post(
            url, json={"callback_query_id": callback_query_id, "text": text},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            pass
    except Exception:
        pass
```

### `engine/supa.py` — `create_contact_from_telegram`

```python
async def create_contact_from_telegram(self, opportunity_id: str, first_name: str) -> bool:
    """Insère un signal de contact depuis Telegram (service_role, bypass RLS).
    Retourne True si créé, False si déjà actif (contrainte unique violée).
    """
    body = f"🤝 {first_name} s'en occupe (via Telegram)"
    url = f"{self.base}/rest/v1/item_comments"
    payload = {"opportunity_id": opportunity_id, "user_id": None,
               "body": body, "type": "contact"}
    headers = self._headers({"Prefer": "return=minimal"})
    async with self.session.post(url, json=payload, headers=headers) as resp:
        if resp.status == 409:   # unique constraint → déjà actif
            return False
        resp.raise_for_status()
        return True
```

### `engine/telegram_bot.py` — coroutine de polling

Nouveau module :

```python
"""Polling des callback_query Telegram (bouton 🤝 Je m'en occupe)."""
import asyncio


async def telegram_poll_worker(brain, supa, telegram, stop_event,
                               poll_pause: float = 3.0) -> None:
    """Interroge getUpdates pour les callback_query 'contact:{opp_id}'.

    Best-effort : toute erreur est loguée sans arrêter la coroutine.
    """
    while not stop_event.is_set():
        try:
            offset = brain.get_telegram_offset()
            updates = await telegram.get_updates(offset=offset)
            for u in updates:
                update_id = u.get("update_id", 0)
                brain.set_telegram_offset(update_id + 1)
                cq = u.get("callback_query")
                if not cq:
                    continue
                data = cq.get("data", "")
                if not data.startswith("contact:"):
                    await telegram.answer_callback(cq["id"], "")
                    continue
                opp_id = data[len("contact:"):]
                first_name = (cq.get("from") or {}).get("first_name") or "Quelqu'un"
                try:
                    created = await supa.create_contact_from_telegram(opp_id, first_name)
                    text = "🤝 Enregistré !" if created else "⚠️ Quelqu'un s'en occupe déjà."
                except Exception as exc:
                    text = f"❌ Erreur ({type(exc).__name__})"
                await telegram.answer_callback(cq["id"], text)
        except Exception as exc:
            print(f"[telegram_bot] erreur polling: {exc}")
        await asyncio.sleep(poll_pause)
```

### `server.py` — démarrer `telegram_poll_worker`

```python
from engine.telegram_bot import telegram_poll_worker

# Dans start_autonomous_engine, si telegram est configuré :
if telegram:
    tasks.append(asyncio.create_task(
        telegram_poll_worker(brain, supa, telegram, stop_event)
    ))
    print("🤝 Polling callbacks Telegram démarré.")
```

## Fichiers modifiés / créés

| Fichier | Action |
|---|---|
| `supabase/migrations/2026-06-04-je-contacte.sql` | Créer |
| `engine/db.py` | Modifier (SCHEMA + 2 méthodes offset) |
| `engine/supa.py` | Modifier (+ `create_contact_from_telegram`) |
| `engine/telegram.py` | Modifier (+ `get_updates`, `answer_callback`, bouton inline) |
| `engine/telegram_bot.py` | Créer (`telegram_poll_worker`) |
| `js/lib/comments.js` | Modifier (SELECT + 2 fonctions + exclure contacts du count) |
| `js/components/comments.js` | Modifier (rendu contact pin + bouton + gestion clics) |
| `style.css` | Modifier (styles contact pin + bouton) |
| `server.py` | Modifier (démarrer telegram_poll_worker) |
| `tests/test_engine_telegram_bot.py` | Créer |
| `tests/test_engine_supa_contact.py` | Créer |
| `tests/test_engine_db_telegram_offset.py` | Créer |

## Tests backend

| Fichier | Tests |
|---|---|
| `test_engine_db_telegram_offset.py` | get/set offset ; idempotent |
| `test_engine_supa_contact.py` | `create_contact_from_telegram` : créé (201) ; déjà actif (409→False) ; erreur réseau best-effort |
| `test_engine_telegram_bot.py` | callback `contact:uuid` → create + answer "Enregistré" ; déjà actif → answer "Quelqu'un" ; callback inconnu → answer "" ; stop_event arrête la boucle |

## Hors scope

- Mapping Telegram ↔ profil hub (prénom suffit pour l'instant)
- Modification du message Telegram après press (pas d'edit_message_reply_markup)
- Historique des contacts annulés visible dans l'UI
- Notif Telegram quand quelqu'un annule le signal
