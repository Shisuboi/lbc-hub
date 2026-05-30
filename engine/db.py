"""Le cerveau SQLite local du moteur : dédup, historique de prix, marché, logs, outbox."""
import sqlite3
import time
import json

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
    blocked_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    retries INTEGER DEFAULT 0
);
"""


class Brain:
    def __init__(self, path: str = "lbc_brain.sqlite3"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

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
