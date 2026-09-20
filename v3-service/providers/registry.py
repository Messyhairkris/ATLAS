"""Provider registry: adds an API-provider, backend-agnostic chat/embedding
trail to the fork. Providers live in ATLAS_PROVIDERS_FILE
(default <repo root>/providers.json); selecting one is ATLAS_PROVIDER=<id>.

Design contract (docs/COMPAT note): providers.json-only entries. Capability
flags describe which *optional* request fields a provider tolerates, so
callers can filter request bodies before sending.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


class ProviderError(Exception):
    pass


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG = _REPO_ROOT / "providers.json"


def _config_path() -> Path:
    return Path(os.environ.get("ATLAS_PROVIDERS_FILE", str(_DEFAULT_CONFIG)))


def load_config() -> Dict[str, Any]:
    try:
        with open(_config_path()) as fh:
            return json.load(fh)
    except OSError:
        return {}
    except json.JSONDecodeError as e:
        raise ProviderError(f"providers config at {_config_path()} is not valid JSON: {e}")


def active_provider_name(explicit: Optional[str] = None) -> Optional[str]:
    """Resolution: explicit arg > ATLAS_PROVIDER env > config default_provider.
    Returns None when nothing opts in; callers must then behave exactly like
    upstream ATLAS."""
    if explicit:
        return explicit
    env = os.environ.get("ATLAS_PROVIDER")
    if env:
        return env
    cfg = load_config()
    return cfg.get("default_provider") or None


def _get_provider(name: Optional[str]) -> Optional[Dict[str, Any]]:
    if not name:
        return None
    cfg = load_config()
    providers = cfg.get("providers", {})
    entry = providers.get(name)
    if entry is None:
        raise ProviderError(
            f"provider '{name}' not found in {_config_path()}; "
            f"available: {sorted(providers)}"
        )
    entry = dict(entry)
    entry.setdefault("capabilities", {})
    return entry


def _resolve_secret(selector: Dict[str, Any]) -> str:
    key_env = selector.get("api_key_env")
    if key_env:
        key = os.environ.get(key_env, "")
        if key:
            return key
    fallback = selector.get("api_key_fallback")
    if fallback:
        cfg_path, dotted = fallback.get("config"), fallback.get("key_selector", "")
        cur: Any = None
        try:
            with open(cfg_path) as fh:
                cur = json.load(fh)
            for part in dotted.split("."):
                cur = cur[part]
            return cur or ""
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            return ""
    return ""


def _headers(entry: Dict[str, Any]) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    auth = entry.get("auth") or {}
    if auth.get("type") == "bearer":
        key = _resolve_secret(auth)
        if key:
            headers["Authorization"] = f"Bearer {key}"
    for k, v in (entry.get("extra_headers") or {}).items():
        headers[k] = v.format(**os.environ)
    return headers


def resolve_alias(provider: Optional[str], model: str) -> str:
    """Human nicknames -> canonical model ids (providers.json model_aliases).
    Case-insensitive; unknown names pass through unchanged."""
    entry = _get_provider(provider)
    aliases = (entry or {}).get("model_aliases") or {}
    for name, canonical in aliases.items():
        if name.lower() == (model or "").lower():
            return canonical
    return model


def nickname_for(provider: Optional[str], model: str) -> str:
    """Reverse lookup for display: canonical id -> nickname (or the id)."""
    entry = _get_provider(provider)
    aliases = (entry or {}).get("model_aliases") or {}
    canonical = {}
    for name, cid in aliases.items():
        canonical.setdefault(cid, name)
    return canonical.get(model, model)


def denied_models(provider: Optional[str] = None) -> set:
    """Canonical ids listed in ATLAS_DENY_MODELS (comma-separated ids or
    nicknames). Lets an operator guarantee a model is NOT called this round
    (e.g. no Kimi while measuring the roster's own Synthetic usage) instead
    of relying on every runner flag being remembered."""
    raw = os.environ.get("ATLAS_DENY_MODELS", "")
    names = [n.strip() for n in raw.split(",") if n.strip()]
    return {resolve_alias(provider, n).lower() for n in names}


def model_pricing(provider: Optional[str], model: str) -> Optional[Dict[str, Any]]:
    """providers.json `pricing` entry for a canonical model id, or None."""
    entry = _get_provider(provider)
    return ((entry or {}).get("pricing") or {}).get(model)


def chat_target(provider: Optional[str] = None, model: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """OpenAI-compatible chat target for the active provider, or None when the
    harness is running in upstream local-llama mode."""
    entry = _get_provider(active_provider_name(provider))
    if entry is None:
        return None
    base = entry["base_url"].rstrip("/")
    name = active_provider_name(provider)
    model_id = resolve_alias(
        name,
        model
        or os.environ.get("ATLAS_CHAT_MODEL")
        or (entry.get("chat_models") or ["default"])[0],
    )
    if model_id.lower() in denied_models(name):
        raise ProviderError(
            f"model '{model_id}' is in ATLAS_DENY_MODELS; refusing to call it")
    return {
        "provider": name,
        "url": f"{base}{entry.get('chat_path', '/v1/chat/completions')}",
        "model": model_id,
        "headers": _headers(entry),
        "capabilities": entry["capabilities"],
        "pricing": ((entry.get("pricing") or {}).get(model_id)),
    }


def embedding_target(provider: Optional[str] = None) -> Optional[Dict[str, Any]]:
    entry = _get_provider(active_provider_name(provider))
    if entry is None:
        return None
    emb = entry.get("embeddings")
    if not emb:
        return None
    base = entry["base_url"].rstrip("/")
    return {
        "provider": active_provider_name(provider),
        "url": f"{base}{emb.get('path', '/v1/embeddings')}",
        "model": emb.get("model", "default"),
        "headers": _headers(entry),
        "billed": bool(emb.get("billed", True)),
    }


_FILTER_FIELDS = {
    "accepts_chat_template_kwargs": ["chat_template_kwargs"],
    "accepts_logprobs": ["logprobs", "top_logprobs"],
    "accepts_seed": ["seed"],
    "accepts_stream_options": ["stream_options"],
    "accepts_reasoning_effort": ["reasoning_effort"],
}


def filter_chat_body(body: Dict[str, Any], capabilities: Dict[str, Any]) -> Dict[str, Any]:
    """Drop request fields the active provider is not known to tolerate.
    Absence of a flag means 'conservative: strip' — llama-server tolerated
    everything, hosted APIs often reject unknown fields."""
    body = dict(body)
    for flag, fields in _FILTER_FIELDS.items():
        if not capabilities.get(flag, False):
            for f in fields:
                body.pop(f, None)
    if not capabilities.get("supports_streaming", True):
        body["stream"] = False
        body.pop("stream_options", None)
    return body
