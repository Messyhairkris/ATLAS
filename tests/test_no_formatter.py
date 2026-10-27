"""Every OpenCode config we write turns formatters off (2026-10-27: rustfmt rewrote whole files
mid-build, so diffs were 90% noise and the model's edits were refused as stale)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_every_opencode_config_writer_disables_formatters():
    writers = [p for p in (ROOT / "crew").rglob("*.py")
               if "opencode.ai/config.json" in p.read_text(encoding="utf-8")]
    assert len(writers) >= 3
    missing = [p.name for p in writers if '"formatter": False' not in p.read_text(encoding="utf-8")]
    assert missing == []


def test_the_chat_engine_config_disables_formatters():
    from crew.runners import pa_session
    assert pa_session.base_config({}, {}, "x", "c")["formatter"] is False
