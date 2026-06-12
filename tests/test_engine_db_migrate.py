import sqlite3
from engine.db import Brain


def test_brain_migrates_old_market_observations_without_model_name(tmp_path):
    """Une base ANCIENNE (market_observations sans model_name) doit migrer sans crasher.

    Reproduit le bug : le SCHEMA créait un index sur model_name AVANT la migration qui
    ajoute la colonne → 'no such column: model_name' sur toute base pré-existante.
    """
    db = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(db)
    # Schéma d'AVANT l'ajout de model_name
    conn.execute(
        "CREATE TABLE market_observations "
        "(categorie TEXT, prix REAL, ville TEXT, observed_at INTEGER NOT NULL)"
    )
    conn.commit()
    conn.close()

    # Ne doit PAS lever
    b = Brain(str(db))
    cols = [r["name"] for r in b.conn.execute(
        "PRAGMA table_info(market_observations)").fetchall()]
    assert "model_name" in cols  # colonne ajoutée par la migration
    # l'index existe aussi
    idx = [r["name"] for r in b.conn.execute(
        "PRAGMA index_list(market_observations)").fetchall()]
    assert "market_obs_model_idx" in idx
    b.close()
