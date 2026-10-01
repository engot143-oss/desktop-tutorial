"""Worker connection adapters (v1.1: manual paste only)."""

from .base import AdapterResult, ConnectionStatus
from .manual import ManualAdapter, create_manual_packet

__all__ = [
    "AdapterResult",
    "ConnectionStatus",
    "ManualAdapter",
    "create_manual_packet",
]
