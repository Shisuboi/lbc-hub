-- Migration : ajouter colonne model_name à market_observations
-- À exécuter manuellement dans le Brain SQLite du laptop si vous avez une base existante

ALTER TABLE market_observations ADD COLUMN model_name TEXT;
CREATE INDEX IF NOT EXISTS market_obs_model_idx ON market_observations(model_name);
