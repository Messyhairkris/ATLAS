"""The MCP catalogue: which extra servers a PA may switch on from chat, and what it may do.

Kris, 2026-10-27, confirmed the risk classes; the design is TheCrew/design/Round 4 - PA tools
and MCP switching.md, sections 1-2. crew/mcp_catalog.json lists one entry per server in Crush's
mcp block (%LOCALAPPDATA%/crush/crush.json), except crew itself, which every PA always has, and
gives each a class. The classes (the same file) say what a PA may do with a server of that
class: read -> allow, local_act -> ask_once, account -> ask, never -> deny. The catalogue is the
policy, so changing it is a settings edit, not a code change.

Nothing here talks to a model or the network. servers() turns each catalogued Crush entry into
an OpenCode mcp entry, ALWAYS disabled (switching one on is crew_mcp's job, crew/server.py);
secrets never land in that output - every header and environment VALUE becomes
{env:CREW_MCP_<NAME>_<KEY>}, and secret_env() hands the real values to the engine's process
alone. decide() is what a caller asks before it does anything.

  python -c "from crew import mcp_catalog as m; print(m.servers(m.load()))"
"""

import json
import os
import re
from pathlib import Path

# Kris edits this; the engine and the tests point elsewhere by argument.
CATALOG = Path(__file__).resolve().parent / "mcp_catalog.json"

# Crush's config, where each entry's command/url/headers/env really live.
CRUSH = (Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
         / "crush" / "crush.json")

ENV_PREFIX = "CREW_MCP"
PLACEHOLDER = "{env:%s}"


def load(path=CATALOG) -> dict:
    """The catalogue as it is written: {"classes": {...}, "servers": [...]}."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def find(catalog: dict, name: str):
    """The catalogue entry for a server name, or None if the catalogue does not know it."""
    for entry in catalog.get("servers") or []:
        if entry.get("from") == name:
            return entry
    return None


def klass(catalog: dict, name: str) -> str:
    """The risk class of a server, or "" if it is not catalogued."""
    return (find(catalog, name) or {}).get("class", "")


def why(catalog: dict, name: str) -> str:
    """The class's one-line reason, for the sentence crew_mcp returns to Kris."""
    entry = find(catalog, name) or {}
    return ((catalog.get("classes") or {}).get(entry.get("class")) or {}).get("_why", "")


def _env_name(server: str, key: str) -> str:
    """The environment variable a secret is passed in: CREW_MCP_<NAME>_<KEY>, upper-cased and
    reduced to A-Z 0-9 _ so any header or env key (Authorization, X-Api-Key) is legal."""
    always = re.sub(r"[^0-9A-Za-z]", "_", f"{server}_{key}")
    return f"{ENV_PREFIX}_{always}".upper()


def _placeholder(server: str, key: str) -> str:
    return PLACEHOLDER % _env_name(server, key)


def _mask(values: dict, server: str) -> dict:
    """The same keys, but every VALUE replaced by its {env:...} reference: a generated config
    may name a secret, never carry one."""
    return {key: _placeholder(server, key) for key in (values or {})}


def _secret_values(values: dict, server: str) -> dict:
    """The real values, keyed by their environment variable, for the engine's process only."""
    out = {}
    for key, value in (values or {}).items():
        out[_env_name(server, key)] = value if isinstance(value, str) else str(value)
    return out


def _entry(src: dict, server: str) -> dict:
    """One OpenCode mcp entry from its Crush entry, always disabled (Kris switches it on from
    chat). A url makes a remote entry (headers masked); anything else is a local command."""
    headers = src.get("headers") or {}
    url = src.get("url")
    if url or src.get("type") in ("http", "sse", "remote"):
        entry = {"type": "remote", "url": url, "enabled": False}
        if headers:
            entry["headers"] = _mask(headers, server)
        return entry
    command = src.get("command")
    argv = list(command) if isinstance(command, list) else [command] + list(src.get("args") or [])
    entry = {"type": "local", "command": [a for a in argv if a is not None], "enabled": False}
    env = src.get("env") or src.get("environment") or {}
    if env:
        entry["environment"] = _mask(env, server)
    return entry


def _block(crush_path) -> dict:
    """Crush's mcp block, or {} if the file is missing, unreadable or malformed."""
    try:
        data = json.loads(Path(crush_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data.get("mcp") or {}


def servers(catalog: dict, crush_path=CRUSH) -> dict:
    """name -> OpenCode mcp entry, built from Crush's, always with "enabled": false. No secret
    value appears: headers and environment values are {env:CREW_MCP_<NAME>_<KEY>} references."""
    block = _block(crush_path)
    out = {}
    for entry in catalog.get("servers") or []:
        name = entry.get("from")
        src = block.get(name)
        if isinstance(src, dict):
            out[name] = _entry(src, name)
    return out


def secret_env(catalog: dict, crush_path=CRUSH) -> dict:
    """The real header/environment values as an env dict, keyed CREW_MCP_<NAME>_<KEY>. For the
    engine's process only (pa_engine adds it to the server's environment); never printed or
    written, the same as the Synthetic key."""
    block = _block(crush_path)
    out = {}
    for entry in catalog.get("servers") or []:
        name = entry.get("from")
        src = block.get(name)
        if not isinstance(src, dict):
            continue
        out.update(_secret_values(src.get("headers") or {}, name))
        out.update(_secret_values(src.get("env") or src.get("environment") or {}, name))
    return out


def _approved(approved_this_chat, name: str) -> bool:
    """True if Kris has already approved this server in this chat: True for all, or a name (or
    a collection of names) that contains it."""
    if not approved_this_chat:
        return False
    if approved_this_chat is True:
        return True
    if isinstance(approved_this_chat, (set, list, tuple, dict)):
        return name in approved_this_chat
    return approved_this_chat == name


def decide(catalog: dict, name: str, action: str, approved_this_chat=False) -> str:
    """What a PA may do with `action` ("on" or "off") on `name`: "allow", "ask" or "deny".

    The catalogue decides everything. An uncatalogued name is a deny, and switching one OFF is
    always allowed (it can only reduce what a PA can reach). For "on", the server's class gives
    the rule: allow -> allow, ask -> ask, deny -> deny, ask_once -> allow only once Kris has
    approved it in this chat.
    """
    if find(catalog, name) is None:
        return "deny"                       # never catalogued is never allowed
    if action == "off":
        return "allow"
    rules = (catalog.get("classes") or {}).get(klass(catalog, name)) or {}
    rule = rules.get(action, "deny")
    if rule == "ask_once":
        return "allow" if _approved(approved_this_chat, name) else "ask"
    if rule in ("allow", "ask", "deny"):
        return rule
    return "deny"                           # an unknown rule is not permission
