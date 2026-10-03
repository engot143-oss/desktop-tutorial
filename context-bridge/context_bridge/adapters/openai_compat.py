"""OpenAI-compatible chat completions adapter (OpenAI, xAI, Ollama, OpenRouter)."""

from __future__ import annotations

from .transport import (
    AdapterNotConfigured,
    PreparedRequest,
    chat_completions_url,
    env_first,
    openai_message_text,
    post_json,
)


class OpenAICompatibleAdapter:
    """Generic chat-completions client. No key required (local Ollama)."""

    name = "openai-compatible"
    require_key = False
    default_model = "llama3.2"
    default_base = "http://localhost:11434/v1"
    key_envs = ("OPENAI_COMPAT_API_KEY", "OLLAMA_API_KEY")
    model_envs = ("OPENAI_COMPAT_MODEL", "OLLAMA_MODEL")
    base_envs = ("OPENAI_COMPAT_BASE_URL", "OLLAMA_BASE_URL")

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
            return (
                f"No endpoint configured for {self.name}. "
                "Set a base URL or use the local Ollama default."
            )
        if self.require_key and not self.api_key:
            return (
                f"{self.key_envs[0]} is not set. "
                "No live call was made."
            )
        return None

    def prepare(self, prompt: str, *, max_tokens: int) -> PreparedRequest:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        url = chat_completions_url(self.base_url or "")
        return PreparedRequest(
            method="POST",
            url=url,
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
        return openai_message_text(data)


class OpenAIAdapter(OpenAICompatibleAdapter):
    """OpenAI Chat Completions (ChatGPT / Glow). Requires OPENAI_API_KEY."""

    name = "openai"
    require_key = True
    default_model = "gpt-4o-mini"
    default_base = "https://api.openai.com/v1"
    key_envs = ("OPENAI_API_KEY",)
    model_envs = ("OPENAI_MODEL",)
    base_envs = ("OPENAI_BASE_URL",)


class XAIAdapter(OpenAICompatibleAdapter):
    """xAI chat completions (Grok). Requires XAI_API_KEY."""

    name = "xai"
    require_key = True
    default_model = "grok-3-mini"
    default_base = "https://api.x.ai/v1"
    key_envs = ("XAI_API_KEY",)
    model_envs = ("XAI_MODEL",)
    base_envs = ("XAI_BASE_URL",)
