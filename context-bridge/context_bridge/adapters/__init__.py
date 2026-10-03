"""Worker connection adapters.

v1.1 manual paste remains the fallback. v1.2 adds live HTTP adapters
(Anthropic, xAI, OpenAI, and a generic OpenAI-compatible endpoint).
"""

from .anthropic import AnthropicAdapter
from .base import AdapterResult, ConnectionStatus
from .manual import ManualAdapter, create_manual_packet
from .openai_compat import OpenAIAdapter, OpenAICompatibleAdapter, XAIAdapter
from .registry import default_provider_for, make_adapter, normalize_provider

__all__ = [
    "AdapterResult",
    "AnthropicAdapter",
    "ConnectionStatus",
    "ManualAdapter",
    "OpenAIAdapter",
    "OpenAICompatibleAdapter",
    "XAIAdapter",
    "create_manual_packet",
    "default_provider_for",
    "make_adapter",
    "normalize_provider",
]
