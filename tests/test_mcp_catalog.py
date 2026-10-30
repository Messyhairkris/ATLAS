"""crew/mcp_catalog.json, crew/mcp_catalog.py and crew/server.crew_mcp (Kris, 2026-10-27).

The catalogue decides what a PA may switch on from chat; these tests hold it to that, over a
fake crush.json in tmp_path. No network: crew_mcp's HTTP call is monkeypatched, so nothing here
opens a socket.

Run: python -m pytest -q tests/test_mcp_catalog.py
"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from crew import mcp_catalog, server  # noqa: E402

TOKEN = "tok-secret-123"          # a fake secret: it must never reach a generated config

# Every server in Crush's mcp block, one per catalogue class. Shapes follow Crush's own
# (type/command/args/env; a remote server is type/url/headers).
CRUSH_MCP = {
    "crew": {"type": "stdio", "command": "python", "args": ["crew_server.py"],
             "env": {"CREW_CLIENT": "Crush"}},
    "hex_analyzer": {"type": "stdio", "command": "hex.exe", "args": ["--serve"],
                     "env": {"HEX_TOKEN": TOKEN}},
    "disasm_helper": {"type": "stdio", "command": "disasm.exe", "args": []},
    "pe_elf_analyzer": {"type": "stdio", "command": "pe.exe", "args": []},
    "document_server": {"type": "stdio", "command": "doc.exe", "args": []},
    "godot_docs": {"type": "stdio", "command": "nodep", "args": ["godot_docs.js"]},
    "godot_docs_full": {"type": "stdio", "command": "nodep", "args": ["godot_docs_full.js"]},
    "arxiv": {"type": "http", "url": "https://arxiv.example/mcp",
              "headers": {"Authorization": f"Bearer {TOKEN}"}},
    "context7": {"type": "http", "url": "https://context7.example/mcp"},
    "shadcn": {"type": "http", "url": "https://shadcn.example/mcp"},
    "godot_mcp": {"type": "stdio", "command": "godot.exe", "args": ["--mcp"]},
    "chrome_devtools": {"type": "stdio", "command": "npx", "args": ["chrome-devtools"]},
    "playwright": {"type": "stdio", "command": "npx", "args": ["playwright"]},
    "obsidian": {"type": "stdio", "command": "obsidian-mcp.exe", "args": []},
    "github": {"type": "http", "url": "https://api.githubcopilot.example/mcp",
               "headers": {"Authorization": f"Bearer {TOKEN}"}},
    "sentry": {"type": "http", "url": "https://sentry.example/mcp"},
    "penpot": {"type": "http", "url": "https://penpot.example/mcp"},
    "penpot_godot_bridge": {"type": "stdio", "command": "python", "args": ["bridge.py"]},
    "notepadpp": {"type": "stdio", "command": "notepadpp-mcp.exe", "args": []},
}


@pytest.fixture()
def crush(tmp_path):
    path = tmp_path / "crush.json"
    path.write_text(json.dumps({"mcp": CRUSH_MCP}), encoding="utf-8")
    return path


def catalog():
    return mcp_catalog.load()


# --- the catalogue itself ---------------------------------------------------

def test_every_crush_server_except_crew_is_catalogued_and_nothing_extra(crush):
    names = [e["from"] for e in catalog()["servers"]]
    assert len(names) == len(set(names)), "a server is catalogued twice"
    assert sorted(names) == sorted(k for k in CRUSH_MCP if k != "crew")


def test_the_generated_config_carries_no_secret_and_nothing_is_on(crush):
    generated = mcp_catalog.servers(catalog(), crush)
    text = json.dumps(generated)
    assert TOKEN not in text, "a secret value reached the generated config"
    assert "{env:CREW_MCP_" in text, "secrets should be {env:...} references"
    assert len(generated) == len(CRUSH_MCP) - 1          # crew is added by pa_session, not here
    for name, entry in generated.items():
        assert entry["enabled"] is False, f"{name} must be generated disabled"


def test_secret_env_has_the_real_values_for_the_engine_only(crush):
    env = mcp_catalog.secret_env(catalog(), crush)
    assert env["CREW_MCP_HEX_ANALYZER_HEX_TOKEN"] == TOKEN
    assert env["CREW_MCP_ARXIV_AUTHORIZATION"] == f"Bearer {TOKEN}"
    assert env["CREW_MCP_GITHUB_AUTHORIZATION"] == f"Bearer {TOKEN}"
    assert env["CREW_MCP_ARXIV_AUTHORIZATION"].startswith("Bearer")


def test_a_stdio_entry_becomes_a_local_command_and_a_url_a_remote_one(crush):
    generated = mcp_catalog.servers(catalog(), crush)
    assert generated["hex_analyzer"]["type"] == "local"
    assert generated["hex_analyzer"]["command"] == ["hex.exe", "--serve"]
    assert generated["arxiv"]["type"] == "remote"
    assert generated["arxiv"]["url"] == "https://arxiv.example/mcp"


# --- decide(): the catalogue decides ---------------------------------------

def test_decide_follows_the_classes():
    cat = catalog()
    assert mcp_catalog.decide(cat, "notepadpp", "on") == "deny"      # never
    assert mcp_catalog.decide(cat, "github", "on") == "ask"          # account
    assert mcp_catalog.decide(cat, "sentry", "on") == "ask"
    assert mcp_catalog.decide(cat, "arxiv", "on") == "allow"         # read
    assert mcp_catalog.decide(cat, "hex_analyzer", "on") == "allow"


def test_decide_asks_once_for_local_act_and_allows_once_approved():
    cat = catalog()
    assert mcp_catalog.decide(cat, "godot_mcp", "on") == "ask"
    assert mcp_catalog.decide(cat, "godot_mcp", "on", True) == "allow"
    assert mcp_catalog.decide(cat, "godot_mcp", "on", ["godot_mcp"]) == "allow"
    assert mcp_catalog.decide(cat, "godot_mcp", "on", ["arxiv"]) == "ask"


def test_decide_allows_switching_off_and_refuses_the_uncatalogued():
    cat = catalog()
    assert mcp_catalog.decide(cat, "notepadpp", "off") == "allow"    # off only reduces reach
    assert mcp_catalog.decide(cat, "unknown_server", "on") == "deny"  # the catalogue decides


# --- crew_mcp: the tool -----------------------------------------------------

@pytest.fixture()
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("CREW_ENGINE_URL", "http://127.0.0.1:4199")
    monkeypatch.setenv("CREW_HOME", str(tmp_path))
    calls = []
    monkeypatch.setattr(server, "_engine_http",
                        lambda method, url, *a, **k: calls.append((method, url)) or {"ok": True})
    return calls, tmp_path


def _log_lines(tmp_path):
    path = tmp_path / "mcp_switch.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_crew_mcp_refuses_a_never_server_and_makes_no_http_call(engine):
    calls, tmp_path = engine
    out = server.crew_mcp("on", "notepadpp", reason="please")
    assert "does not allow" in out
    assert calls == [], "a refused server must not be connected"
    lines = _log_lines(tmp_path)
    assert len(lines) == 1 and lines[0]["decision"] == "deny"


def test_crew_mcp_asks_for_an_account_server_and_makes_no_http_call(engine):
    calls, tmp_path = engine
    out = server.crew_mcp("on", "github", reason="open an issue")
    assert "Kris must approve" in out
    assert calls == [], "an account server needs Kris, never a silent connect"
    assert _log_lines(tmp_path)[0]["decision"] == "ask"


def test_crew_mcp_on_a_read_server_connects_once_and_writes_one_log_line(engine):
    calls, tmp_path = engine
    out = server.crew_mcp("on", "arxiv", reason="find papers")
    assert json.loads(out)["decision"] == "allow"
    assert len(calls) == 1
    method, url = calls[0]
    assert method == "POST"
    assert "/mcp/arxiv/connect" in url
    assert "directory=" in url, "the engine holds several projects and must be told which"
    lines = _log_lines(tmp_path)
    assert len(lines) == 1
    line = lines[0]
    assert line["client"] == server.CLIENT and line["action"] == "on" and line["name"] == "arxiv"
    assert line["decision"] == "allow" and line["reason"] == "find papers"
    assert line["ts"]


def test_crew_mcp_off_disconnects(engine):
    calls, _ = engine
    server.crew_mcp("off", "arxiv", reason="done")
    assert len(calls) == 1
    assert calls[0][0] == "POST" and "/mcp/arxiv/disconnect" in calls[0][1]


def test_crew_mcp_list_names_class_and_state(engine, monkeypatch):
    monkeypatch.setattr(server, "_engine_http",
                        lambda method, url, *a, **k: {"arxiv": {"status": "connected"}})
    listing = json.loads(server.crew_mcp("list"))
    by = {e["name"]: e for e in listing}
    assert len(listing) == len(CRUSH_MCP) - 1
    assert by["arxiv"] == {"name": "arxiv", "class": "read", "on": True}
    assert by["notepadpp"]["class"] == "never" and by["notepadpp"]["on"] is False


def test_crew_mcp_without_the_engine_says_so_and_does_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("CREW_ENGINE_URL", raising=False)
    monkeypatch.setenv("CREW_HOME", str(tmp_path))
    calls = []
    monkeypatch.setattr(server, "_engine_http",
                        lambda method, url, *a, **k: calls.append((method, url)) or {})
    out = server.crew_mcp("on", "arxiv")
    assert out == "switching needs The Crew's engine"
    assert calls == []
    assert not (tmp_path / "mcp_switch.jsonl").exists(), "do nothing includes writing no log"
