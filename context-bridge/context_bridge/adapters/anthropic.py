"""Anthropic Messages API adapter (Claude). Stdlib HTTP only."""

from __future__ import annotations

from .transport import (
    AdapterNotConfigured,
    PreparedRequest,
    anthropic_message_text,
    anthropic_messages_url,
    env_first,
    post_json,
)


class AnthropicAdapter:
    """Claude via https://api.anthropic.com/v1/messages. Requires ANTHROPIC_API_KEY."""

    name = "anthropic"
    require_key = True
    default_model = "claude-haiku-4-5"
    default_base = "https://api.anthropic.com"
    key_envs = ("ANTHROPIC_API_KEY",)
    model_envs = ("ANTHROPIC_MODEL",)
    base_envs = ("ANTHROPIC_BASE_URL",)

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        if api_key is None:
            api_key = env_first(self.key_envs)
        self.api_key = (api_key or "").strip() or None

        if base_url is None:
            base_url = env_first(self.base_envs) or self.default_base
        self.base_url = (base_url or "").strip() or None

        if model is None:
            model = env_first(self.model_envs) or self.default_model
        self.model = (model or "").strip() or self.default_model

    def unavailable_reason(self) -> str | None:
        if not self.base_url:
            return "No endpoint configured for anthropic."
        if not self.api_key:
            return "ANTHROPIC_API_KEY is not set. No live call was made."
        return None

    def prepare(self, prompt: str, *, max_tokens: int) -> PreparedRequest:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        return PreparedRequest(
            method="POST",
            url=anthropic_messages_url(self.base_url or ""),
            headers=headers,
            body=body,
            provider=self.name,
            model=self.model,
            secrets=[self.api_key] if self.api_key else [],
        )

    def invoke(self, prompt: str, *, max_tokens: int, timeout: float) -> str:
        reason = self.unavailable_reason()
        if reason:
            raise AdapterNotConfigured(reason)
        req = self.prepare(prompt, max_tokens=max_tokens)
        data = post_json(req, timeout=timeout)
        return anthropic_message_text(data)
