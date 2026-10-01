"""Adapter interface — structure for manual now, live later."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ConnectionStatus(str, Enum):
    """Distinguish unavailable connection vs attempted-but-failed call."""

    UNAVAILABLE = "unavailable"  # no authorized live connection
    FAILED = "failed"  # live call attempted and failed
    AWAITING_EXECUTION = "awaiting_execution"  # manual packet ready for paste
    SUCCESS = "success"  # reserved for future live adapters


@dataclass
class AdapterResult:
    worker: str  # claude | grok
    status: ConnectionStatus
    task_id: str
    packet_path: str | None = None
    error_class: str | None = None
    error_message: str | None = None
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @property
    def flag_type(self) -> str:
        if self.status == ConnectionStatus.UNAVAILABLE:
            return "connection_unavailable"
        if self.status == ConnectionStatus.FAILED:
            return "failed_call"
        return self.status.value
