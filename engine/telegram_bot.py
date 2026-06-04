"""Polling des callback_query Telegram (bouton 🤝 Je m'en occupe)."""
from __future__ import annotations
import asyncio


async def telegram_poll_worker(
    brain, supa, telegram, stop_event,
    poll_pause: float = 3.0,
) -> None:
    """Boucle de polling des callback_query Telegram.

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
                cq_id = cq.get("id", "")

                if not data.startswith("contact:"):
                    await telegram.answer_callback(cq_id, "")
                    continue

                opp_id = data[len("contact:"):]
                first_name = (cq.get("from") or {}).get("first_name") or "Quelqu'un"

                try:
                    created = await supa.create_contact_from_telegram(opp_id, first_name)
                    text = "🤝 Enregistré !" if created else "⚠️ Quelqu'un s'en occupe déjà."
                except Exception as exc:
                    text = f"❌ Erreur ({type(exc).__name__})"
                    print(f"[telegram_bot] erreur création signal : {exc}")

                await telegram.answer_callback(cq_id, text)

        except Exception as exc:
            print(f"[telegram_bot] erreur polling : {exc}")

        await asyncio.sleep(poll_pause if poll_pause else 0)
