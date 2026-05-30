# tests/test_engine_config.py
import pytest
from engine.config import load_config


def test_load_config_reads_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "SUPABASE_URL=https://demo.supabase.co\n"
        "SUPABASE_SERVICE_KEY=secret123\n",
        encoding="utf-8",
    )
    cfg = load_config(str(env))
    assert cfg["SUPABASE_URL"] == "https://demo.supabase.co"
    assert cfg["SUPABASE_SERVICE_KEY"] == "secret123"


def test_load_config_ignores_comments_and_blanks(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# commentaire\n\nSUPABASE_URL=https://x.co\nSUPABASE_SERVICE_KEY=k\n",
        encoding="utf-8",
    )
    cfg = load_config(str(env))
    assert cfg["SUPABASE_URL"] == "https://x.co"


def test_load_config_missing_key_raises(tmp_path):
    env = tmp_path / ".env"
    env.write_text("SUPABASE_URL=https://x.co\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="SUPABASE_SERVICE_KEY"):
        load_config(str(env))


def test_env_var_overrides_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "SUPABASE_URL=https://file.co\nSUPABASE_SERVICE_KEY=from_file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SUPABASE_URL", "https://env.co")
    cfg = load_config(str(env))
    assert cfg["SUPABASE_URL"] == "https://env.co"
