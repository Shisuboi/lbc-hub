"""Destination locale pour le scrape : met les opportunités brutes en file d'enrichissement.

Interface identique à engine.supa.Supa.insert_opportunity → process_search (Phase A)
l'utilise tel quel. En Phase B, le démon injecte ce sink au lieu du client Supabase direct,
pour que Supabase ne reçoive QUE des opportunités enrichies (via enrichment_worker).
"""


class LocalSink:
    """Enqueue les opportunités brutes dans la file d'enrichissement locale."""

    def __init__(self, brain):
        """
        Args:
            brain: instance Brain avec queue_pending().
        """
        self.brain = brain

    async def insert_opportunity(self, payload: dict) -> None:
        """Enqueue un payload brut dans la file d'enrichissement.

        Args:
            payload: dict avec ad_id, source_search_id (optionnel), et autres champs.
        """
        self.brain.queue_pending(
            payload,
            search_id=payload.get("source_search_id"),
            ad_id=payload.get("ad_id"),
        )
