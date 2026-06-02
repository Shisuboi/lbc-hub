"""Le cerveau SQLite local du moteur : dédup, historique de prix, marché, logs, outbox."""
import sqlite3
import time
import json
from datetime import datetime, timezone, timedelta

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_ads (
    ad_id TEXT PRIMARY KEY,
    first_seen_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    last_price REAL,
    prev_price REAL,
    status TEXT DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS price_observations (
    ad_id TEXT NOT NULL,
    price REAL NOT NULL,
    observed_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS price_obs_ad_idx ON price_observations(ad_id);

CREATE TABLE IF NOT EXISTS market_observations (
    categorie TEXT,
    prix REAL,
    ville TEXT,
    observed_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS market_obs_cat_idx ON market_observations(categorie);

CREATE TABLE IF NOT EXISTS scrape_log (
    search_id TEXT,
    last_run_at INTEGER NOT NULL,
    status TEXT,
    blocked_count INTEGER DEFAULT 0,
    new_ads INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    retries INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pending_enrichment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_id TEXT NOT NULL,
    search_id TEXT,
    payload TEXT NOT NULL,
    queued_at INTEGER NOT NULL,
    retries INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS pending_ad_idx ON pending_enrichment(ad_id);

CREATE TABLE IF NOT EXISTS llm_usage (
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    day TEXT NOT NULL,
    request_count INTEGER DEFAULT 0,
    token_count INTEGER DEFAULT 0,
    PRIMARY KEY (provider, model, day)
);
"""

# Approximation du reset minuit Pacifique (offset fixe, zéro dépendance tzdata).
_PACIFIC_OFFSET = timedelta(hours=-8)


def quota_day(ts: int | None = None) -> str:
    """Jour-quota au format 'YYYY-MM-DD' (~minuit Pacifique, offset fixe -8h)."""
    t = ts if ts is not None else time.time()
    dt = datetime.fromtimestamp(t, tz=timezone.utc) + _PACIFIC_OFFSET
    return dt.strftime("%Y-%m-%d")


class Brain:
    def __init__(self, path: str = "lbc_brain.sqlite3"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Migrations légères des bases déjà créées (CREATE TABLE IF NOT EXISTS ne les altère pas)."""
        cols = [r["name"] for r in self.conn.execute("PRAGMA table_info(scrape_log)").fetchall()]
        if "new_ads" not in cols:
            self.conn.execute("ALTER TABLE scrape_log ADD COLUMN new_ads INTEGER DEFAULT 0")

    def close(self) -> None:
        self.conn.close()

    def upsert_ad(self, ad_id: str, price: float, now: int | None = None) -> str:
        """Retourne 'new', 'price_drop' ou 'seen'. Enregistre une observation si le prix change."""
        now = int(now if now is not None else time.time())
        row = self.conn.execute(
            "SELECT last_price FROM seen_ads WHERE ad_id = ?", (ad_id,)
        ).fetchone()

        if row is None:
            self.conn.execute(
                "INSERT INTO seen_ads (ad_id, first_seen_at, last_seen_at, last_price, prev_price) "
                "VALUES (?, ?, ?, ?, NULL)",
                (ad_id, now, now, price),
            )
            self.conn.execute(
                "INSERT INTO price_observations (ad_id, price, observed_at) VALUES (?, ?, ?)",
                (ad_id, price, now),
            )
            self.conn.commit()
            return "new"

        last_price = row["last_price"]
        event = "seen"
        if last_price is None or price != last_price:
            self.conn.execute(
                "INSERT INTO price_observations (ad_id, price, observed_at) VALUES (?, ?, ?)",
                (ad_id, price, now),
            )
            self.conn.execute(
                "UPDATE seen_ads SET last_seen_at = ?, prev_price = last_price, last_price = ? WHERE ad_id = ?",
                (now, price, ad_id),
            )
            if last_price is not None and price < last_price:
                event = "price_drop"
        else:
            self.conn.execute(
                "UPDATE seen_ads SET last_seen_at = ? WHERE ad_id = ?", (now, ad_id)
            )
        self.conn.commit()
        return event

    def previous_price(self, ad_id: str) -> float | None:
        row = self.conn.execute(
            "SELECT prev_price FROM seen_ads WHERE ad_id = ?", (ad_id,)
        ).fetchone()
        return row["prev_price"] if row else None

    def record_market_obs(self, categorie: str, prix: float, ville: str | None, now: int | None = None) -> None:
        now = int(now if now is not None else time.time())
        self.conn.execute(
            "INSERT INTO market_observations (categorie, prix, ville, observed_at) VALUES (?, ?, ?, ?)",
            (categorie, prix, ville, now),
        )
        self.conn.commit()

    def log_scrape(self, search_id: str, status: str, blocked: int = 0,
                   new_ads: int = 0, now: int | None = None) -> None:
        now = int(now if now is not None else time.time())
        self.conn.execute(
            "INSERT INTO scrape_log (search_id, last_run_at, status, blocked_count, new_ads) "
            "VALUES (?, ?, ?, ?, ?)",
            (search_id, now, status, blocked, new_ads),
        )
        self.conn.commit()

    def new_ads_rate(self, search_id: str, window_s: int = 600, now: int | None = None) -> float:
        """Annonces neuves par minute sur la fenêtre glissante (moyenne)."""
        now = int(now if now is not None else time.time())
        row = self.conn.execute(
            "SELECT COALESCE(SUM(new_ads), 0) AS s FROM scrape_log "
            "WHERE search_id = ? AND last_run_at >= ?",
            (search_id, now - window_s),
        ).fetchone()
        minutes = window_s / 60.0
        return (float(row["s"] or 0) / minutes) if minutes else 0.0

    def ads_seen_total(self, search_id: str) -> int:
        """Cumul d'annonces uniques que cette recherche a fait remonter (somme des new_ads)."""
        row = self.conn.execute(
            "SELECT COALESCE(SUM(new_ads), 0) AS s FROM scrape_log WHERE search_id = ?",
            (search_id,),
        ).fetchone()
        return int(row["s"] or 0)

    def last_pass_at(self, search_id: str) -> int | None:
        row = self.conn.execute(
            "SELECT MAX(last_run_at) AS m FROM scrape_log WHERE search_id = ?",
            (search_id,),
        ).fetchone()
        return row["m"] if row and row["m"] is not None else None

    def blocked_recent(self, search_id: str, window_s: int = 600, now: int | None = None) -> int:
        now = int(now if now is not None else time.time())
        row = self.conn.execute(
            "SELECT COALESCE(SUM(blocked_count), 0) AS s FROM scrape_log "
            "WHERE search_id = ? AND last_run_at >= ?",
            (search_id, now - window_s),
        ).fetchone()
        return int(row["s"] or 0)

    def queue_outbox(self, payload: dict, now: int | None = None) -> None:
        now = int(now if now is not None else time.time())
        self.conn.execute(
            "INSERT INTO outbox (payload, created_at, retries) VALUES (?, ?, 0)",
            (json.dumps(payload), now),
        )
        self.conn.commit()

    def peek_outbox(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, payload, retries FROM outbox ORDER BY id ASC LIMIT ?", (limit,)
        ).fetchall()
        return [{"id": r["id"], "payload": json.loads(r["payload"]), "retries": r["retries"]} for r in rows]

    def delete_outbox(self, outbox_id: int) -> None:
        self.conn.execute("DELETE FROM outbox WHERE id = ?", (outbox_id,))
        self.conn.commit()

    def queue_pending(self, payload: dict, search_id: str | None, ad_id: str, now: int | None = None) -> None:
        now = int(now if now is not None else time.time())
        self.conn.execute(
            "INSERT INTO pending_enrichment (ad_id, search_id, payload, queued_at, retries) VALUES (?, ?, ?, ?, 0)",
            (ad_id, search_id, json.dumps(payload), now),
        )
        self.conn.commit()

    def peek_pending(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, ad_id, search_id, payload, retries FROM pending_enrichment ORDER BY id ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"id": r["id"], "ad_id": r["ad_id"], "search_id": r["search_id"],
             "payload": json.loads(r["payload"]), "retries": r["retries"]}
            for r in rows
        ]

    def delete_pending(self, pending_id: int) -> None:
        self.conn.execute("DELETE FROM pending_enrichment WHERE id = ?", (pending_id,))
        self.conn.commit()

    def bump_pending_retry(self, pending_id: int) -> None:
        self.conn.execute(
            "UPDATE pending_enrichment SET retries = retries + 1 WHERE id = ?", (pending_id,)
        )
        self.conn.commit()

    def inc_usage(self, provider: str, model: str, day: str, tokens: int = 0) -> None:
        self.conn.execute(
            "INSERT INTO llm_usage (provider, model, day, request_count, token_count) "
            "VALUES (?, ?, ?, 1, ?) "
            "ON CONFLICT(provider, model, day) DO UPDATE SET "
            "request_count = request_count + 1, token_count = token_count + excluded.token_count",
            (provider, model, day, tokens),
        )
        self.conn.commit()

    def usage_count(self, provider: str, model: str, day: str) -> int:
        row = self.conn.execute(
            "SELECT request_count FROM llm_usage WHERE provider = ? AND model = ? AND day = ?",
            (provider, model, day),
        ).fetchone()
        return row["request_count"] if row else 0
