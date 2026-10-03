"""Stdlib HTTP transport for live adapters. Never logs or returns API keys."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .. import __version__

# Low-cost defaults. A single call cannot exceed the cap.
DEFAULT_MAX_TOKENS = 1024
MAX_TOKENS_CAP = 4096
DEFAULT_TIMEOUT_S = 60.0
TIMEOUT_CAP_S = 120.0
TIMEOUT_FLOOR_S = 0.1

_SECRET_HEADER_NAMES = {
    "authorization",
    "x-api-key",
    "api-key",
    "x-goog-api-key",
    "openai-api-key",
}


class AdapterNotConfigured(Exception):
    """No key or endpoint. The live call was not attempted."""

    error_class = "connection_unavailable"


class LiveCallFailed(Exception):
    """A live call was attempted and did not return usable text."""

    def __init__(self, message: str, error_class: str = "live_call_failed"):
        super().__init__(message)
        self.error_class = error_class


def redact_secrets(text: str, secrets: list[str] | None) -> str:
    """Replace exact secret values. Ignores empty and very short strings."""
    if not text or not secrets:
        return text or ""
    out = text
    for secret in sorted({s for s in secrets if s and len(s) >= 8}, key=len, reverse=True):
        out = out.replace(secret, "[REDACTED]")
    return out


def resolve_max_tokens(value: int | None, *, env_raw: str | None = None) -> tuple[int, str | None]:
    """Return (capped_tokens, note). Note is set when the requested value was lowered."""
    note = None
    if value is None:
        raw = (env_raw or "").strip()
        if raw:
            try:
                value = int(raw)
            except ValueError:
                return DEFAULT_MAX_TOKENS, "CB_MAX_TOKENS was not an integer; using the default."
        else:
            value = DEFAULT_MAX_TOKENS
    if value < 1:
        value = 1
    if value > MAX_TOKENS_CAP:
        return MAX_TOKENS_CAP, f"max_tokens capped at {MAX_TOKENS_CAP}."
    return value, note


def resolve_timeout(value: float | None, *, env_raw: str | None = None) -> tuple[float, str | None]:
    """Return (capped_seconds, note)."""
    note = None
    if value is None:
        raw = (env_raw or "").strip()
        if raw:
            try:
                value = float(raw)
            except ValueError:
                return DEFAULT_TIMEOUT_S, "CB_TIMEOUT was not a number; using the default."
        else:
            value = DEFAULT_TIMEOUT_S
    if value < TIMEOUT_FLOOR_S:
        value = TIMEOUT_FLOOR_S
    if value > TIMEOUT_CAP_S:
        return TIMEOUT_CAP_S, f"timeout capped at {int(TIMEOUT_CAP_S)}s."
    return float(value), note


def env_first(names: tuple[str, ...]) -> str | None:
    import os

    for name in names:
        raw = os.environ.get(name)
        if raw is not None and raw.strip():
            return raw.strip()
    return None


def normalize_openai_base(url: str) -> str:
    """Ensure an OpenAI-compatible base ends in /v1 when the path is empty.

    `http://localhost:11434` becomes `http://localhost:11434/v1`.
    `https://openrouter.ai/api/v1` is left unchanged.
    """
    base = url.strip().rstrip("/")
    if not base:
        return base
    if base.endswith("/v1"):
        return base
    parts = urllib.parse.urlsplit(base)
    if parts.path in ("", "/"):
        return base + "/v1"
    return base


def anthropic_messages_url(base: str) -> str:
    b = base.strip().rstrip("/")
    if b.endswith("/v1"):
        return b + "/messages"
    return b + "/v1/messages"


def chat_completions_url(base: str) -> str:
    return normalize_openai_base(base) + "/chat/completions"


def dumps_body(body: dict[str, Any]) -> str:
    """Canonical body text. Dry-run prints this exact string."""
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


@dataclass
class PreparedRequest:
    method: str
    url: str
    headers: dict[str, str]
    body: dict[str, Any]
    provider: str
    model: str
    secrets: list[str] = field(default_factory=list)

    def body_text(self) -> str:
        return dumps_body(self.body)

    def public_headers(self) -> dict[str, str]:
        """Headers safe to print. Secret header values are never copied."""
        out: dict[str, str] = {}
        for key, value in self.headers.items():
            if key.lower() in _SECRET_HEADER_NAMES:
                stripped = (value or "").strip()
                if not stripped or stripped.lower() in ("bearer",):
                    out[key] = "[MISSING]"
                elif stripped.lower().startswith("bearer "):
                    token = stripped[7:].strip()
                    out[key] = "Bearer [REDACTED]" if token else "Bearer [MISSING]"
                else:
                    out[key] = "[REDACTED]"
            else:
                out[key] = redact_secrets(value, self.secrets)
        return out


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so an Authorization header cannot leave the endpoint."""

    def http_error_302(self, req, fp, code, msg, headers):  # noqa: ANN001
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)

    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302
    http_error_308 = http_error_302


def _open(req: urllib.request.Request, timeout: float):
    opener = urllib.request.build_opener(_NoRedirect)
    return opener.open(req, timeout=timeout)


def _safe_url(url: str, secrets: list[str]) -> str:
    parts = urllib.parse.urlsplit(url)
    if parts.username or parts.password:
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        url = urllib.parse.urlunsplit((parts.scheme, host, parts.path, "", ""))
    return redact_secrets(url, secrets)


def finalize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Headers that actually go on the wire, minus nothing secret (caller redacts)."""
    out = dict(headers)
    out.setdefault("Content-Type", "application/json")
    out.setdefault("Accept", "application/json")
    out.setdefault("User-Agent", f"context-bridge/{__version__}")
    return out


def post_json(req: PreparedRequest, *, timeout: float) -> dict[str, Any]:
    """POST JSON. Raises LiveCallFailed on failure. Does not follow redirects."""
    payload = req.body_text().encode("utf-8")
    headers = finalize_headers(req.headers)
    request = urllib.request.Request(
        req.url,
        data=payload,
        headers=headers,
        method=req.method or "POST",
    )
    try:
        with _open(request, timeout) as resp:
            raw = resp.read()
    except LiveCallFailed:
        raise
    except urllib.error.HTTPError as exc:
        snippet = ""
        try:
            snippet = exc.read().decode("utf-8", errors="replace")[:180]
        except Exception:
            snippet = ""
        snippet = redact_secrets(snippet, req.secrets)
        detail = f"HTTP {exc.code} from provider"
        if snippet.strip():
            detail = f"{detail}: {snippet.strip()}"
        raise LiveCallFailed(detail, "http_error") from None
    except (TimeoutError, socket.timeout):
        raise LiveCallFailed(f"Timed out after {timeout:g}s", "timeout") from None
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise LiveCallFailed(f"Timed out after {timeout:g}s", "timeout") from None
        kind = type(reason).__name__ if reason is not None else "URLError"
        url = _safe_url(req.url, req.secrets)
        if isinstance(reason, ConnectionRefusedError):
            message = f"Could not reach provider endpoint (connection refused): {url}"
        else:
            message = f"Could not reach provider endpoint ({kind}): {url}"
        raise LiveCallFailed(message, "connection_error") from None
    except OSError as exc:
        url = _safe_url(req.url, req.secrets)
        raise LiveCallFailed(
            f"Could not reach provider endpoint ({type(exc).__name__}): {url}",
            "connection_error",
        ) from None

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LiveCallFailed("Provider response was not UTF-8 text", "bad_response") from exc
    text = redact_secrets(text, req.secrets)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LiveCallFailed("Provider response was not JSON", "bad_response") from exc
    if not isinstance(data, dict):
        raise LiveCallFailed("Provider response JSON was not an object", "bad_response")
    return data


def openai_message_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices or not isinstance(choices, list):
        raise LiveCallFailed("Response had no choices", "bad_response")
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    text = _content_to_text(content)
    if not text.strip():
        raise LiveCallFailed("Response content was empty", "bad_response")
    return text


def anthropic_message_text(data: dict[str, Any]) -> str:
    text = _content_to_text(data.get("content"))
    if not text.strip():
        raise LiveCallFailed("Anthropic response content was empty", "bad_response")
    return text


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                if part.get("type") in (None, "text", "output_text") and part.get("text"):
                    parts.append(str(part.get("text")))
                elif part.get("content"):
                    parts.append(_content_to_text(part.get("content")))
        return "".join(parts)
    return ""
