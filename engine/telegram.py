"""Notifications Telegram pour le moteur autonome.

Deux fonctions publiques best-effort (jamais bloquantes) :
- send_opportunity(client, opp) → groupe partagé (opportunité 🔴)
- send_alert(client, text)      → DM Tristan (captcha, alertes techniques)
"""
from __future__ import annotations

import aiohttp
import json as _json

HUB_BASE = "https://shisuboi.github.io/lbc-hub"
TG_API = "https://api.telegram.org/bot{token}/sendMessage"
TG_UPDATES_API = "https://api.telegram.org/bot{token}/getUpdates"
TG_ANSWER_API = "https://api.telegram.org/bot{token}/answerCallbackQuery"


class TelegramClient:
    """Wrapper minimal vers l'API Telegram Bot."""

    def __init__(self, token: str, group_id: str, tristan_id: str,
                 session: aiohttp.ClientSession):
        self.token = token
        self.group_id = group_id
        self.tristan_id = tristan_id
        self.session = session

    async def get_updates(self, offset: int = 0) -> list[dict]:
        """Récupère les callback_query depuis l'offset. Best-effort."""
        try:
            url = TG_UPDATES_API.format(token=self.token)
            async with self.session.post(
                url,
                json={"offset": offset, "timeout": 5, "allowed_updates": ["callback_query"]},
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
            url = TG_ANSWER_API.format(token=self.token)
            async with self.session.post(
                url,
                json={"callback_query_id": callback_query_id, "text": text},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status >= 400:
                    print(f"[telegram] erreur answer_callback (HTTP {resp.status})")
        except Exception as exc:
            print(f"[telegram] erreur answer_callback : {exc}")


def _esc(s) -> str:
    """Échappe les 3 caractères réservés du parse_mode HTML de Telegram (& < >).

    On utilise HTML (et non Markdown) : un titre Leboncoin contient souvent des caractères
    qui cassent le Markdown (_ * [ ] ( )) et provoquent un HTTP 400 « can't parse entities ».
    En HTML, seuls & < > doivent être échappés ; tout le reste passe littéralement.
    """
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _format_opportunity(opp: dict) -> str:
    """Formate un message HTML pour une opportunité 🔴 (robuste aux titres arbitraires)."""
    title = opp.get("title") or "Sans titre"
    price = opp.get("price")
    margin = opp.get("est_margin_eur")
    city = opp.get("location_city")
    url = opp.get("url", "")
    opp_id = opp.get("id") or opp.get("ad_id", "")

    lines = [f"🔴 <b>{_esc(title)}</b>", ""]
    if price is not None:
        lines.append(f"💰 Prix : {int(price)} €")
    if margin and float(margin) > 0:
        lines.append(f"📈 Marge estimée : +{int(margin)} €")
    if city:
        lines.append(f"📍 {_esc(city)}")
    lines.append("")
    if url:
        lines.append(f'🔗 <a href="{_esc(url)}">Voir sur LBC</a>')
    if opp_id:
        lines.append(f'🏠 <a href="{HUB_BASE}/item/{opp_id}">Voir sur le hub</a>')

    return "\n".join(lines)


async def send_opportunity(client: TelegramClient, opp: dict) -> bool:
    """Envoie une notification d'opportunité 🔴 au groupe.

    Best-effort (ne lève jamais) mais renvoie True SEULEMENT si l'envoi a réussi (HTTP 2xx).
    L'appelant doit ne marquer l'annonce « notifiée » que sur un True → sinon un échec
    transitoire (400/réseau) la supprimerait définitivement sans qu'elle soit jamais envoyée.
    """
    try:
        opp_id = opp.get("id") or opp.get("ad_id", "")
        body = {
            "chat_id": client.group_id,
            "text": _format_opportunity(opp),
            "parse_mode": "HTML",
        }
        if opp_id:
            body["reply_markup"] = _json.dumps({
                "inline_keyboard": [[{
                    "text": "🤝 Je m'en occupe",
                    "callback_data": f"contact:{opp_id}",
                }]]
            })
        url = TG_API.format(token=client.token)
        async with client.session.post(
            url, json=body,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status >= 400:
                txt = await resp.text()
                print(f"[telegram] erreur envoi opportunité (HTTP {resp.status}): {txt[:200]}")
                return False
            return True
    except Exception as exc:
        print(f"[telegram] erreur envoi opportunité : {exc}")
        return False


async def answer_callback(client: TelegramClient, callback_query_id: str, text: str) -> None:
    """Wrapper module-level → délègue à client.answer_callback."""
    await client.answer_callback(callback_query_id, text)


async def send_alert(client: TelegramClient, text: str) -> None:
    """Envoie une alerte technique en DM à Tristan. Best-effort."""
    try:
        url = TG_API.format(token=client.token)
        async with client.session.post(
            url,
            json={"chat_id": client.tristan_id, "text": text},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                print(f"[telegram] erreur envoi alerte (HTTP {resp.status}): {body[:200]}")
    except Exception as exc:
        print(f"[telegram] erreur envoi alerte : {exc}")
