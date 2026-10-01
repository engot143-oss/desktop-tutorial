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
    (re.compile(r"\b(sk-[A-Za-z0-9_-]{16,})\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]+=*"), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"\b(AKIA[0-9A-Z]{16})\b"), "[REDACTED_AWS_KEY]"),
    (
        re.compile(
            r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|token)"
            r"\s*[=:]\s*\S+"
        ),
        r"\1=[REDACTED]",
    ),
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


def scrub_key(key: Any) -> str:
    """
    Scrub a dict key. Credential-named keys become [REDACTED_KEY];
    keys containing free-text secrets are scrubbed in place.
    """
    k = str(key)
    if k == "credentials_included":
        return k
    if _CRED_KEYS.search(k):
        return "[REDACTED_KEY]"
    scrubbed = scrub_text(k)
    return scrubbed


def _unique_key(base: str, used: set[str]) -> str:
    if base not in used:
        return base
    i = 2
    while f"{base}#{i}" in used:
        i += 1
    return f"{base}#{i}"


def scrub_obj(obj: Any, *, root: bool = False) -> Any:
    """
    Recursively scrub credential-like keys (renamed) and free-text patterns.
    Handles key collisions from redaction by suffixing #2, #3, …
    Sets credentials_included=False only on the root dict.
    """
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        used: set[str] = set()
        for k, v in obj.items():
            if k == "credentials_included":
                continue
            new_k = scrub_key(k)
            new_k = _unique_key(new_k, used)
            used.add(new_k)
            if _CRED_KEYS.search(str(k)):
                out[new_k] = "[REDACTED]"
            else:
                out[new_k] = scrub_obj(v, root=False)
        if root:
            out["credentials_included"] = False
        return out
    if isinstance(obj, list):
        return [scrub_obj(x, root=False) for x in obj]
    if isinstance(obj, str):
        return scrub_text(obj)
    return obj
