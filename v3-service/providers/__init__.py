"""Config-driven LLM provider layer for the ATLAS API harness fork.

Backward compatible: with ATLAS_PROVIDER unset, every call site falls back to
the upstream local-llama behavior exactly. Opting in is an environment choice,
not a code change.
"""

from .registry import (
    chat_target,
    embedding_target,
    filter_chat_body,
    active_provider_name,
    ProviderError,
)
from .telemetry import record as record_call
from .telemetry import context as telemetry_context

__all__ = [
    "chat_target",
    "embedding_target",
    "filter_chat_body",
    "active_provider_name",
    "record_call",
    "telemetry_context",
    "ProviderError",
]
