"""Resolve a worker role to a live adapter."""

from __future__ import annotations

from .anthropic import AnthropicAdapter
from .openai_compat import OpenAIAdapter, OpenAICompatibleAdapter, XAIAdapter

LIVE_WORKERS = ("claude", "grok", "glow", "chatgpt")

_ALIASES = {
    "ollama": "openai-compatible",
    "compat": "openai-compatible",
    "openai-compat": "openai-compatible",
    "openai_compatible": "openai-compatible",
}

_DEFAULT_PROVIDER = {
    "claude": "anthropic",
    "grok": "xai",
    "glow": "openai",
    "chatgpt": "openai",
}

PROVIDERS = {
    "anthropic": AnthropicAdapter,
    "xai": XAIAdapter,
    "openai": OpenAIAdapter,
    "openai-compatible": OpenAICompatibleAdapter,
}


def normalize_provider(name: str) -> str:
    key = (name or "").strip().lower().replace("_", "-")
    key = _ALIASES.get(key, key)
    if key not in PROVIDERS:
        known = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"Unknown provider '{name}'. Expected one of: {known}.")
    return key


def default_provider_for(worker: str) -> str:
    try:
        return _DEFAULT_PROVIDER[worker]
    except KeyError as exc:
        raise ValueError(
            "worker must be claude, grok, glow, or chatgpt"
        ) from exc


def make_adapter(
    provider: str,
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
):
    """Build a live adapter. Explicit model/base_url/api_key override env and defaults."""
    cls = PROVIDERS[normalize_provider(provider)]
    return cls(model=model, base_url=base_url, api_key=api_key)
