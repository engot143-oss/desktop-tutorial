"""Credential scrubbing for keys and free-text patterns before export."""

from __future__ import annotations

import re
from typing import Any

# Key names that look like secrets (nested dicts)
_CRED_KEYS = re.compile(
    r"(password|secret|api[_-]?key|token|credential|private[_-]?key|auth|"
    r"access[_-]?key|session[_-]?id|bearer)",
    re.IGNORECASE,
)

# Free-text patterns (values / prose)
_FREE_TEXT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # OpenAI / similar sk-... keys
    (re.compile(r"\b(sk-[A-Za-z0-9_-]{16,})\b"), "[REDACTED_API_KEY]"),
    # Bearer tokens
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]+=*"), "Bearer [REDACTED_TOKEN]"),
    # AWS access key id
    (re.compile(r"\b(AKIA[0-9A-Z]{16})\b"), "[REDACTED_AWS_KEY]"),
    # Explicit assignments: password=..., token: ..., api_key=...
    (
        re.compile(
            r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|token)"
            r"\s*[=:]\s*\S+"
        ),
        r"\1=[REDACTED]",
    ),
    # PEM private key blocks
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
]


def scrub_text(text: str) -> str:
    """Redact credential-like patterns in free text."""
    if not text:
        return text
    out = text
    for pattern, repl in _FREE_TEXT_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def scrub_obj(obj: Any, *, root: bool = False) -> Any:
    """
    Recursively scrub credential-like keys and free-text patterns.
    Sets credentials_included=False only on the root dict.
    """
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k == "credentials_included":
                continue
            if _CRED_KEYS.search(str(k)):
                out[k] = "[REDACTED]"
            else:
                out[k] = scrub_obj(v, root=False)
        if root:
            out["credentials_included"] = False
        return out
    if isinstance(obj, list):
        return [scrub_obj(x, root=False) for x in obj]
    if isinstance(obj, str):
        return scrub_text(obj)
    return obj
