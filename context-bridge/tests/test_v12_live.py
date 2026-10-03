"""v1.2 live adapters: localhost stub only. No real provider calls."""

from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from context_bridge import __version__
from context_bridge import store
from context_bridge.adapters.anthropic import AnthropicAdapter
from context_bridge.adapters.openai_compat import (
    OpenAIAdapter,
    OpenAICompatibleAdapter,
    XAIAdapter,
)
from context_bridge.adapters.registry import make_adapter
from context_bridge.adapters.transport import (
    MAX_TOKENS_CAP,
    anthropic_message_text,
    chat_completions_url,
    normalize_openai_base,
    openai_message_text,
)
from context_bridge.cli import main
from context_bridge.live_send import send_hop
from context_bridge.models import GlowPlan

ROOT = Path(__file__).resolve().parent.parent

SK_KEY = "sk-contextbridgeunittestvalue123456789"
XAI_KEY = "xai-contextbridgeunittestvalue123456789"

_ENV_KEYS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_BASE_URL",
    "XAI_API_KEY",
    "XAI_MODEL",
    "XAI_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_BASE_URL",
    "OPENAI_COMPAT_API_KEY",
    "OPENAI_COMPAT_MODEL",
    "OPENAI_COMPAT_BASE_URL",
    "OLLAMA_API_KEY",
    "OLLAMA_MODEL",
    "OLLAMA_BASE_URL",
    "CB_MAX_TOKENS",
    "CB_TIMEOUT",
)

RESULT_MD = """# Result — HAB-1

| Field | Value |
|-------|--------|
| Project | Habitat Sensors |
| Task ID | HAB-1 |
| Based on version | 1.2.0 |
| Author | Claude |

## Changes
- Added the sensor loop.

## Verification evidence
- Stub returned this result.

## Blockers
- None.

## Next action
Glow reads the return pack.

## Decisions
- Keep the manual packet as the fallback.
"""


def _openai_payload(text: str) -> bytes:
    return json.dumps(
        {"choices": [{"message": {"role": "assistant", "content": text}}]}
    ).encode("utf-8")


def _anthropic_payload(text: str) -> bytes:
    return json.dumps(
        {"content": [{"type": "text", "text": text}]}
    ).encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b""
        server: _Server = self.server  # type: ignore[assignment]
        server.hits.append(
            {
                "path": self.path,
                "body": raw.decode("utf-8"),
                "headers": {k.lower(): v for k, v in self.headers.items()},
            }
        )
        if server.mode == "sleep":
            time.sleep(server.delay)
        if server.mode == "redirect":
            self.send_response(302)
            self.send_header("Location", "/evil")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if server.mode == "echo":
            auth = self.headers.get("Authorization", "")
            xkey = self.headers.get("x-api-key", "")
            text = f"echoed-auth {auth} echoed-key {xkey}"
            payload = _openai_payload(text)
        elif server.mode == "status":
            payload = server.payload
            self.send_response(server.status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except OSError:
                return
            return
        else:
            payload = server.payload
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except OSError:
            return

    def log_message(self, fmt, *args):  # noqa: A003
        return


class _Server(ThreadingHTTPServer):
    def __init__(self, address, handler):
        super().__init__(address, handler)
        self.hits: list[dict] = []
        self.mode = "ok"
        self.payload = b"{}"
        self.status_code = 500
        self.delay = 0.0
        self.daemon_threads = True


class Stub:
    def __init__(self, mode="ok", payload=b"{}", status=500, delay=0.0):
        self.httpd = _Server(("127.0.0.1", 0), _Handler)
        self.httpd.mode = mode
        self.httpd.payload = payload
        self.httpd.status_code = status
        self.httpd.delay = delay
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self) -> str:
        host, port = self.httpd.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def hits(self) -> list[dict]:
        return self.httpd.hits

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def _body_of(preview: str) -> str:
    return preview.split("--- body ---\n", 1)[1].split("\n--- end ---", 1)[0]


def _closed_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class V12Base(unittest.TestCase):
    def setUp(self):
        self._saved_env = {key: os.environ.get(key) for key in _ENV_KEYS}
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        self.tmp = Path(tempfile.mkdtemp(prefix="cb-v12-"))
        self._orig_data = store.DATA_DIR
        store.DATA_DIR = self.tmp / "projects"
        self._open_guard = patch(
            "context_bridge.adapters.transport._open",
            side_effect=AssertionError("unexpected network call"),
        )

    def tearDown(self):
        store.DATA_DIR = self._orig_data
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.tmp, ignore_errors=True)

    def project(self, *, goal_suffix: str = "") -> None:
        ctx = store.ensure_project("Habitat Sensors", repo_path="/tmp/habitat")
        ctx.current_task_id = "HAB-1"
        ctx.current_version = "1.2.0"
        ctx.decisions = ["Manual paste stays the fallback."]
        goal = "Ship the habitat sensor."
        if goal_suffix:
            goal = f"{goal} {goal_suffix}"
        ctx.glow_plan = GlowPlan(
            goal=goal,
            constraints=["stdlib only"],
            open_questions=["Which model is cheapest?"],
            who_gets_what_next={
                "Claude": "Implement the sensor loop",
                "Grok": "Review the approach",
                "Glow": "Read the return pack",
            },
        )
        store.save_context(ctx)

    def run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def assert_tree_clean(self, *secrets: str) -> None:
        if not self.tmp.exists():
            return
        for path in self.tmp.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for secret in secrets:
                self.assertNotIn(secret, text, f"{secret} leaked into {path}")


class VersionAndDefaultsTests(V12Base):
    def test_package_version(self):
        with self.assertRaises(SystemExit) as caught:
            with redirect_stdout(StringIO()) as out:
                main(["--version"])
        self.assertEqual(caught.exception.code, 0)
        self.assertIn("Context Bridge 1.2.0", out.getvalue())
        self.assertEqual(__version__, "1.2.0")

    def test_low_cost_defaults_and_base_urls(self):
        self.assertEqual(AnthropicAdapter().default_model, "claude-3-5-haiku-latest")
        self.assertEqual(AnthropicAdapter().model, "claude-3-5-haiku-latest")
        self.assertEqual(XAIAdapter().default_model, "grok-3-mini")
        self.assertEqual(OpenAIAdapter().default_model, "gpt-4o-mini")
        compat = OpenAICompatibleAdapter()
        self.assertEqual(compat.default_model, "llama3.2")
        self.assertEqual(compat.default_base, "http://localhost:11434/v1")
        self.assertIsNone(compat.unavailable_reason())
        self.assertIn("is not set", OpenAIAdapter().unavailable_reason() or "")
        self.assertIn("is not set", XAIAdapter().unavailable_reason() or "")
        self.assertIn("is not set", AnthropicAdapter().unavailable_reason() or "")

    def test_base_url_normalization(self):
        self.assertEqual(
            normalize_openai_base("http://localhost:11434"),
            "http://localhost:11434/v1",
        )
        self.assertEqual(
            normalize_openai_base("https://openrouter.ai/api/v1"),
            "https://openrouter.ai/api/v1",
        )
        self.assertEqual(
            chat_completions_url("http://localhost:11434"),
            "http://localhost:11434/v1/chat/completions",
        )
        ollama = make_adapter("ollama")
        self.assertIsInstance(ollama, OpenAICompatibleAdapter)
        self.assertEqual(ollama.name, "openai-compatible")

    def test_message_parsers(self):
        text = openai_message_text(
            {"choices": [{"message": {"content": [{"type": "text", "text": "hi"}]}}]}
        )
        self.assertEqual(text, "hi")
        text = anthropic_message_text(
            {"content": [{"type": "text", "text": "claude"}, {"type": "text", "text": " ok"}]}
        )
        self.assertEqual(text, "claude ok")


class AdapterStubTests(V12Base):
    def test_each_adapter_posts_to_stub(self):
        cases = [
            (
                "anthropic",
                AnthropicAdapter,
                "/v1/messages",
                _anthropic_payload("claude-text"),
                "claude-text",
                "x-api-key",
                SK_KEY,
            ),
            (
                "openai",
                OpenAIAdapter,
                "/v1/chat/completions",
                _openai_payload("openai-text"),
                "openai-text",
                "authorization",
                f"Bearer {SK_KEY}",
            ),
            (
                "xai",
                XAIAdapter,
                "/v1/chat/completions",
                _openai_payload("grok-text"),
                "grok-text",
                "authorization",
                f"Bearer {XAI_KEY}",
            ),
            (
                "openai-compatible",
                OpenAICompatibleAdapter,
                "/v1/chat/completions",
                _openai_payload("local-text"),
                "local-text",
                None,
                None,
            ),
        ]
        for provider, cls, path, payload, expected, header, secret in cases:
            with self.subTest(provider=provider):
                stub = Stub(payload=payload)
                try:
                    kwargs = {
                        "base_url": stub.base_url,
                        "model": f"model-{provider}",
                    }
                    if secret and provider != "openai-compatible":
                        kwargs["api_key"] = SK_KEY if provider != "xai" else XAI_KEY
                    adapter = cls(**kwargs)
                    if provider == "openai-compatible":
                        self.assertIsNone(adapter.api_key)
                    reply = adapter.invoke("ping", max_tokens=32, timeout=5)
                    self.assertEqual(reply, expected)
                    self.assertEqual(len(stub.hits), 1)
                    hit = stub.hits[0]
                    self.assertEqual(hit["path"], path)
                    body = json.loads(hit["body"])
                    self.assertEqual(body["model"], f"model-{provider}")
                    self.assertEqual(body["max_tokens"], 32)
                    self.assertEqual(body["messages"][0]["content"], "ping")
                    if header:
                        self.assertEqual(hit["headers"][header], secret)
                        self.assertNotIn(secret, reply)
                    else:
                        self.assertNotIn("authorization", hit["headers"])
                finally:
                    stub.close()

    def test_http_error_timeout_and_redirect(self):
        stub = Stub(mode="status", payload=f'{{"err":"{SK_KEY}"}}'.encode(), status=500)
        try:
            adapter = OpenAIAdapter(api_key=SK_KEY, base_url=stub.base_url, model="m")
            with self.assertRaises(Exception) as caught:
                adapter.invoke("ping", max_tokens=16, timeout=5)
            self.assertEqual(caught.exception.error_class, "http_error")
            self.assertNotIn(SK_KEY, str(caught.exception))
        finally:
            stub.close()

        stub = Stub(mode="sleep", payload=_openai_payload("late"), delay=1.0)
        try:
            adapter = OpenAIAdapter(api_key=SK_KEY, base_url=stub.base_url, model="m")
            with self.assertRaises(Exception) as caught:
                adapter.invoke("ping", max_tokens=16, timeout=0.2)
            self.assertEqual(caught.exception.error_class, "timeout")
        finally:
            stub.close()

        stub = Stub(mode="redirect")
        try:
            adapter = OpenAIAdapter(api_key=SK_KEY, base_url=stub.base_url, model="m")
            with self.assertRaises(Exception) as caught:
                adapter.invoke("ping", max_tokens=16, timeout=5)
            self.assertEqual(caught.exception.error_class, "http_error")
            self.assertEqual(len(stub.hits), 1)
            self.assertNotIn(SK_KEY, str(caught.exception))
        finally:
            stub.close()


class SendFallbackTests(V12Base):
    def test_missing_keys_fall_back_unavailable_without_network(self):
        self.project()
        with self._open_guard:
            for worker, provider in (
                ("claude", "anthropic"),
                ("grok", "xai"),
                ("glow", "openai"),
            ):
                with self.subTest(worker=worker):
                    code, out, err = self.run_cli(
                        ["send", "Habitat Sensors", worker, "--task-id", "HAB-1"]
                    )
                    self.assertEqual(err, "")
                    self.assertEqual(code, 3, out)
                    self.assertIn("FALLBACK", out)
                    self.assertIn("connection: unavailable", out)
                    self.assertIn("error_class: connection_unavailable", out)
                    self.assertIn(provider, out)
        self.assertTrue(any((self.tmp / "projects").rglob("*.md")))
        ctx = store.load_context("Habitat Sensors")
        types = {flag["type"] for flag in ctx.flags}
        self.assertIn("connection_unavailable", types)
        self.assertNotIn("failed_call", types)
        # Plan survived every fallback.
        self.assertEqual(ctx.glow_plan.goal, "Ship the habitat sensor.")
        self.assertIn("Manual paste stays the fallback.", ctx.decisions)

    def test_http_failure_is_failed_not_unavailable(self):
        self.project()
        os.environ["OPENAI_API_KEY"] = SK_KEY
        stub = Stub(
            mode="status",
            status=503,
            payload=f"upstream {SK_KEY}".encode(),
        )
        try:
            code, out, err = self.run_cli(
                [
                    "send",
                    "Habitat Sensors",
                    "claude",
                    "--provider",
                    "openai",
                    "--base-url",
                    stub.base_url,
                    "--timeout",
                    "5",
                ]
            )
        finally:
            stub.close()
        self.assertEqual(code, 3, out + err)
        self.assertIn("connection: failed", out)
        self.assertIn("error_class: http_error", out)
        self.assertNotIn(SK_KEY, out)
        self.assertNotIn(SK_KEY, err)
        self.assertEqual(len(stub.hits), 1)
        ctx = store.load_context("Habitat Sensors")
        self.assertTrue(any(flag["type"] == "failed_call" for flag in ctx.flags))
        self.assert_tree_clean(SK_KEY)

    def test_timeout_and_connection_refused(self):
        self.project()
        os.environ["XAI_API_KEY"] = XAI_KEY
        stub = Stub(mode="sleep", payload=_openai_payload("late"), delay=1.0)
        try:
            code, out, _err = self.run_cli(
                [
                    "send",
                    "Habitat Sensors",
                    "grok",
                    "--provider",
                    "xai",
                    "--base-url",
                    stub.base_url,
                    "--timeout",
                    "0.2",
                ]
            )
        finally:
            stub.close()
        self.assertEqual(code, 3, out)
        self.assertIn("error_class: timeout", out)
        self.assertIn("connection: failed", out)
        self.assertNotIn(XAI_KEY, out)
        self.assert_tree_clean(XAI_KEY)

        self.project()
        port = _closed_port()
        code, out, err = self.run_cli(
            [
                "send",
                "Habitat Sensors",
                "claude",
                "--provider",
                "openai-compatible",
                "--base-url",
                f"http://127.0.0.1:{port}",
                "--timeout",
                "2",
            ]
        )
        self.assertEqual(code, 3, out + err)
        self.assertIn("FALLBACK: manual packet", out)
        self.assertIn("connection: failed", out)
        self.assertIn("status: awaiting_execution", out)
        # A closed local port refuses immediately on some systems and times
        # out on others (Windows). Either class is the same manual fallback.
        self.assertTrue(
            "error_class: connection_error" in out
            or "error_class: timeout" in out,
            out,
        )
        packet_line = next(
            line for line in out.splitlines() if line.startswith("  packet: ")
        )
        packet_path = Path(packet_line.split("packet:", 1)[1].strip())
        self.assertTrue(packet_path.is_file(), packet_path)
        self.assertIn("awaiting_execution", packet_path.read_text(encoding="utf-8"))
        ctx = store.load_context("Habitat Sensors")
        self.assertTrue(ctx.glow_plan)
        self.assertEqual(ctx.glow_plan.goal, "Ship the habitat sensor.")
        self.assertIn("Manual paste stays the fallback.", ctx.decisions)
        self.assertTrue(any(flag["type"] == "failed_call" for flag in ctx.flags))

    def test_empty_endpoint_is_unavailable(self):
        self.project()
        ctx = store.load_context("Habitat Sensors")
        with self._open_guard:
            outcome = send_hop(
                ctx,
                "claude",
                provider="openai-compatible",
                base_url="",
                timeout=2,
            )
        self.assertTrue(outcome.fell_back)
        self.assertEqual(outcome.result.error_class, "connection_unavailable")
        self.assertEqual(outcome.result.details["underlying"], "unavailable")

    def test_unexpected_exception_falls_back_and_scrubs(self):
        self.project()
        os.environ["OPENAI_API_KEY"] = SK_KEY

        def boom(self, prompt, *, max_tokens, timeout):  # noqa: ANN001
            raise RuntimeError(f"exploded {SK_KEY}")

        with patch("context_bridge.adapters.openai_compat.OpenAIAdapter.invoke", boom):
            code, out, err = self.run_cli(
                [
                    "send",
                    "Habitat Sensors",
                    "chatgpt",
                    "--provider",
                    "openai",
                    "--base-url",
                    "http://127.0.0.1:9",
                    "--timeout",
                    "2",
                ]
            )
        self.assertEqual(code, 3, out + err)
        self.assertIn("error_class: live_call_failed", out)
        self.assertIn("connection: failed", out)
        self.assertNotIn(SK_KEY, out)
        self.assertNotIn(SK_KEY, err)
        self.assert_tree_clean(SK_KEY)
        ctx = store.load_context("Habitat Sensors")
        self.assertEqual(ctx.current_task_id, "HAB-1")


class DryRunTests(V12Base):
    def test_dry_run_matches_live_body_and_hides_key(self):
        self.project(goal_suffix=SK_KEY)
        os.environ["OPENAI_API_KEY"] = SK_KEY
        stub = Stub(payload=_openai_payload(RESULT_MD))
        try:
            code, preview, err = self.run_cli(
                [
                    "send",
                    "Habitat Sensors",
                    "claude",
                    "--provider",
                    "openai",
                    "--model",
                    "unit-test-model",
                    "--base-url",
                    stub.base_url,
                    "--max-tokens",
                    "99999",
                    "--dry-run",
                ]
            )
            self.assertEqual(code, 0, preview + err)
            self.assertEqual(stub.hits, [])
            self.assertIn("would_send=yes", preview)
            self.assertIn("max_tokens capped at 4096", preview)
            self.assertIn("Authorization: Bearer [REDACTED]", preview)
            self.assertNotIn(SK_KEY, preview)
            self.assertIn(f"max_tokens={MAX_TOKENS_CAP}", preview)
            body = _body_of(preview)
            parsed = json.loads(body)
            self.assertEqual(parsed["model"], "unit-test-model")
            self.assertEqual(parsed["max_tokens"], MAX_TOKENS_CAP)
            self.assertNotIn(SK_KEY, parsed["messages"][0]["content"])
            self.assertIn("[REDACTED_API_KEY]", parsed["messages"][0]["content"])
            self.assertIn("Goal", parsed["messages"][0]["content"])
            self.assertIn("Who gets what next", parsed["messages"][0]["content"])

            code, out, err = self.run_cli(
                [
                    "send",
                    "Habitat Sensors",
                    "claude",
                    "--provider",
                    "openai",
                    "--model",
                    "unit-test-model",
                    "--base-url",
                    stub.base_url,
                    "--max-tokens",
                    "99999",
                    "--timeout",
                    "5",
                ]
            )
            self.assertEqual(code, 0, out + err)
            self.assertEqual(stub.hits[0]["body"], body)
            self.assertIn(SK_KEY, stub.hits[0]["headers"]["authorization"])
        finally:
            stub.close()

        self.assertNotIn(SK_KEY, out)
        self.assert_tree_clean(SK_KEY)
        packets = list((self.tmp / "projects").rglob("*packet*"))
        self.assertEqual(packets, [])
        ctx = store.load_context("Habitat Sensors")
        self.assertIn("Manual paste stays the fallback.", ctx.decisions)
        self.assertIn("Keep the manual packet as the fallback.", ctx.decisions)
        self.assertTrue((store.project_dir(ctx.project) / "glow_returns" / "latest.json").exists())

    def test_dry_run_does_not_touch_context_or_closed_port(self):
        self.project()
        ctx_before = (store.project_dir("Habitat Sensors") / "context.json").read_text()
        port = _closed_port()
        os.environ["ANTHROPIC_API_KEY"] = SK_KEY
        code, out, err = self.run_cli(
            [
                "send",
                "Habitat Sensors",
                "claude",
                "--provider",
                "anthropic",
                "--base-url",
                f"http://127.0.0.1:{port}",
                "--dry-run",
            ]
        )
        self.assertEqual(code, 0, out + err)
        self.assertIn("would_send=yes", out)
        self.assertIn("/v1/messages", out)
        self.assertIn("x-api-key: [REDACTED]", out)
        self.assertNotIn(SK_KEY, out)
        ctx_after = (store.project_dir("Habitat Sensors") / "context.json").read_text()
        self.assertEqual(ctx_before, ctx_after)
        self.assertFalse(list(self.tmp.rglob("*packet*")))

    def test_dry_run_without_key_shows_request_and_does_not_call(self):
        self.project()
        with self._open_guard:
            code, out, err = self.run_cli(
                ["send", "Habitat Sensors", "grok", "--dry-run"]
            )
        self.assertEqual(code, 0, out + err)
        self.assertIn("provider=xai", out)
        self.assertIn("model=grok-3-mini", out)
        self.assertIn("would_send=no", out)
        self.assertIn("https://api.x.ai/v1/chat/completions", out)
        self.assertIn("XAI_API_KEY is not set", out)
        self.assertNotIn("Bearer sk-", out)
        ctx = store.load_context("Habitat Sensors")
        self.assertEqual(ctx.flags, [])

    def test_model_env_and_compat_free_path_preview(self):
        self.project()
        os.environ["OLLAMA_MODEL"] = "qwen2.5"
        os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"
        with self._open_guard:
            code, out, err = self.run_cli(
                [
                    "send",
                    "Habitat Sensors",
                    "claude",
                    "--provider",
                    "ollama",
                    "--dry-run",
                ]
            )
        self.assertEqual(code, 0, out + err)
        self.assertIn("provider=openai-compatible", out)
        self.assertIn("model=qwen2.5", out)
        self.assertIn("would_send=yes", out)
        self.assertIn("http://127.0.0.1:9/v1/chat/completions", out)
        parsed = json.loads(_body_of(out))
        self.assertEqual(parsed["model"], "qwen2.5")
        self.assertNotIn("authorization", out.lower())


class SendSuccessTests(V12Base):
    def test_live_hop_imports_result_and_writes_glow_pack(self):
        self.project()
        os.environ["ANTHROPIC_API_KEY"] = SK_KEY
        os.environ["ANTHROPIC_MODEL"] = "claude-test-mini"
        stub = Stub(payload=_anthropic_payload(RESULT_MD))
        try:
            code, out, err = self.run_cli(
                [
                    "send",
                    "Habitat Sensors",
                    "claude",
                    "--base-url",
                    stub.base_url,
                    "--timeout",
                    "5",
                ]
            )
        finally:
            stub.close()
        self.assertEqual(code, 0, out + err)
        self.assertIn("Live hop complete", out)
        self.assertIn("provider: anthropic", out)
        self.assertIn("model: claude-test-mini", out)
        self.assertIn("status: success", out)
        self.assertNotIn(SK_KEY, out)
        self.assertEqual(stub.hits[0]["path"], "/v1/messages")
        self.assertEqual(stub.hits[0]["headers"]["x-api-key"], SK_KEY)
        self.assertEqual(stub.hits[0]["headers"]["anthropic-version"], "2023-06-01")
        ctx = store.load_context("Habitat Sensors")
        self.assertIn("Keep the manual packet as the fallback.", ctx.decisions)
        self.assertIn("Manual paste stays the fallback.", ctx.decisions)
        self.assertFalse(any(f["type"] == "failed_call" for f in ctx.flags))
        pack = json.loads(
            (store.project_dir(ctx.project) / "glow_returns" / "latest.json").read_text()
        )
        self.assertEqual(pack["task_id"], "HAB-1")
        self.assertEqual(pack["based_on_version"], "1.2.0")
        self.assertIn("Added the sensor loop.", pack["findings"])
        self.assertTrue(pack["verification_evidence"])
        self.assert_tree_clean(SK_KEY)

    def test_non_result_reply_is_preserved(self):
        self.project()
        os.environ["OPENAI_COMPAT_BASE_URL"] = "http://127.0.0.1:9"
        stub = Stub(payload=_openai_payload("hello from the stub"))
        try:
            # Point the free adapter at the stub. No key.
            code, out, err = self.run_cli(
                [
                    "send",
                    "Habitat Sensors",
                    "grok",
                    "--provider",
                    "openai-compatible",
                    "--base-url",
                    stub.base_url,
                    "--model",
                    "llama3.2",
                    "--timeout",
                    "5",
                ]
            )
        finally:
            stub.close()
        self.assertEqual(code, 0, out + err)
        self.assertIn("status: success", out)
        ctx = store.load_context("Habitat Sensors")
        self.assertEqual(ctx.glow_plan.goal, "Ship the habitat sensor.")
        self.assertIn("Manual paste stays the fallback.", ctx.decisions)
        pack = json.loads(
            (store.project_dir(ctx.project) / "glow_returns" / "latest.json").read_text()
        )
        self.assertIn("hello from the stub", pack.get("raw_markdown", ""))
        self.assertGreaterEqual(pack["flag_summary"]["missing_evidence"], 1)
        blob = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in self.tmp.rglob("*")
            if path.is_file()
        )
        self.assertIn("hello from the stub", blob)

    def test_echoed_nonpattern_key_is_scrubbed(self):
        self.project(goal_suffix=XAI_KEY)
        os.environ["XAI_API_KEY"] = XAI_KEY
        stub = Stub(mode="echo")
        try:
            code, out, err = self.run_cli(
                [
                    "send",
                    "Habitat Sensors",
                    "grok",
                    "--base-url",
                    stub.base_url,
                    "--timeout",
                    "5",
                ]
            )
        finally:
            stub.close()
        self.assertEqual(code, 0, out + err)
        self.assertNotIn(XAI_KEY, out)
        self.assertNotIn(XAI_KEY, err)
        sent = stub.hits[0]["body"]
        self.assertNotIn(XAI_KEY, sent)
        self.assertIn("[REDACTED]", sent)
        self.assert_tree_clean(XAI_KEY)

    def test_unknown_provider_is_an_error(self):
        self.project()
        with self._open_guard:
            code, _out, err = self.run_cli(
                ["send", "Habitat Sensors", "claude", "--provider", "nope"]
            )
        self.assertEqual(code, 1)
        self.assertIn("Unknown provider", err)
        ctx = store.load_context("Habitat Sensors")
        self.assertEqual(ctx.flags, [])


if __name__ == "__main__":
    unittest.main()
