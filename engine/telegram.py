"""Notifications Telegram pour le moteur autonome.

Deux fonctions publiques best-effort (jamais bloquantes) :
- send_opportunity(client, opp) → groupe partagé (opportunité 🔴)
- send_alert(client, text)      → DM Tristan (captcha, alertes techniques)
"""
from __future__ import annotations

import aiohttp

HUB_BASE = "https://shisuboi.github.io/lbc-hub"
TG_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramClient:
    """Wrapper minimal vers l'API Telegram Bot."""

    def __init__(self, token: str, group_id: str, tristan_id: str,
                 session: aiohttp.ClientSession):
        self.token = token
        self.group_id = group_id
        self.tristan_id = tristan_id
        self.session = session


def _format_opportunity(opp: dict) -> str:
    """Formate un message Markdown pour une opportunité 🔴."""
    title = opp.get("title") or "Sans titre"
    price = opp.get("price")
    margin = opp.get("est_margin_eur")
    city = opp.get("location_city")
    url = opp.get("url", "")
    opp_id = opp.get("id") or opp.get("ad_id", "")

    lines = [f"🔴 *{title}*", ""]
    if price is not None:
        lines.append(f"💰 Prix : {int(price)} €")
    if margin and float(margin) > 0:
        lines.append(f"📈 Marge estimée : +{int(margin)} €")
    if city:
        lines.append(f"📍 {city}")
    lines.append("")
    if url:
        lines.append(f"🔗 [Voir sur LBC]({url})")
    if opp_id:
        lines.append(f"🏠 [Voir sur le hub]({HUB_BASE}/item/{opp_id})")

    return "\n".join(lines)


async def send_opportunity(client: TelegramClient, opp: dict) -> None:
    """Envoie une notification d'opportunité 🔴 au groupe. Best-effort."""
    try:
        url = TG_API.format(token=client.token)
        async with client.session.post(
            url,
            json={"chat_id": client.group_id, "text": _format_opportunity(opp),
                  "parse_mode": "Markdown"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                print(f"[telegram] erreur envoi opportunité (HTTP {resp.status}): {body[:200]}")
    except Exception as exc:
        print(f"[telegram] erreur envoi opportunité : {exc}")


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
