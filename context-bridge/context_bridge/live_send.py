"""One live hop: build packet prompt, call adapter, import Result, or fall back."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import store
from .adapters.base import AdapterResult, ConnectionStatus
from .adapters.manual import create_manual_packet
from .adapters.registry import (
    LIVE_WORKERS,
    default_provider_for,
    make_adapter,
    normalize_provider,
)
from .adapters.transport import (
    AdapterNotConfigured,
    LiveCallFailed,
    finalize_headers,
    redact_secrets,
    resolve_max_tokens,
    resolve_timeout,
)
from .export import build_handoff, render_markdown
from .glow_pack import write_glow_return_pack
from .models import ProjectContext, utc_now_iso
from .result_import import ResultImportError, apply_result, load_result, parse_result_markdown
from .scrub import scrub_text

_WORKER_LABELS = {
    "claude": "Claude",
    "grok": "Grok",
    "glow": "Glow",
    "chatgpt": "ChatGPT",
}

_SECRET_ENV_NAMES = (
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_COMPAT_API_KEY",
    "OLLAMA_API_KEY",
)

_FENCE_OPEN = re.compile(r"^```[A-Za-z0-9_-]*\s*$")


@dataclass
class SendOutcome:
    exit_code: int
    fell_back: bool
    dry_run: bool
    would_send: bool
    preview: str = ""
    result: AdapterResult | None = None
    result_path: str | None = None
    glow_md: str | None = None
    glow_json: str | None = None
    provider: str = ""
    model: str = ""
    note: str = ""


def known_secrets(extra: list[str] | None = None) -> list[str]:
    found: list[str] = []
    for name in _SECRET_ENV_NAMES:
        raw = os.environ.get(name, "")
        if raw and len(raw.strip()) >= 8:
            found.append(raw.strip())
    for item in extra or []:
        if item and len(item) >= 8:
            found.append(item)
    # Longest first so a key that contains another key is removed whole.
    return sorted(set(found), key=len, reverse=True)


def scrub_outbound(text: str, secrets: list[str]) -> str:
    return scrub_text(redact_secrets(text or "", secrets))


def redact_context(ctx: ProjectContext, secrets: list[str]) -> None:
    """Strip known API keys from context before it is saved or packeted."""
    if not secrets:
        return

    def clean(value: str | None) -> str:
        return scrub_outbound(value or "", secrets)

    if ctx.repo_path:
        ctx.repo_path = clean(ctx.repo_path)
    if ctx.current_task_id:
        ctx.current_task_id = clean(ctx.current_task_id)
    ctx.current_version = clean(ctx.current_version)
    ctx.decisions = [clean(item) for item in ctx.decisions]
    ctx.assumptions = [clean(item) for item in ctx.assumptions]
    if ctx.glow_plan:
        plan = ctx.glow_plan
        plan.goal = clean(plan.goal)
        plan.constraints = [clean(item) for item in plan.constraints]
        plan.open_questions = [clean(item) for item in plan.open_questions]
        plan.who_gets_what_next = {
            clean(name): clean(action) for name, action in plan.who_gets_what_next.items()
        }
        plan.raw_sections = {
            str(key): clean(value) for key, value in (plan.raw_sections or {}).items()
        }
    for task in ctx.assigned_tasks:
        task.assignee = clean(task.assignee)
        task.tasks = [clean(item) for item in task.tasks]
        task.completion_criteria = clean(task.completion_criteria)
        if task.blocked_until:
            task.blocked_until = clean(task.blocked_until)
    ctx.flags = json.loads(clean(json.dumps(ctx.flags)))
    ctx.decision_history = json.loads(clean(json.dumps(ctx.decision_history)))


def build_worker_prompt(ctx: ProjectContext, worker: str, secrets: list[str]) -> str:
    label = _WORKER_LABELS[worker]
    handoff = build_handoff(ctx, label, source="Context Bridge live adapter")
    body = render_markdown(handoff)
    instructions = (
        f"You are the {label} worker in Context Bridge.\n"
        "Hierarchy: Eric → Glow → Grok Bot → Claude (coding) / Grok (explore).\n"
        "Execute the assigned work in the handoff below.\n"
        "Reply with ONLY a Result in Markdown. Use these sections exactly:\n"
        "Changes, Verification evidence, Blockers, Next action, Decisions.\n"
        "Include this metadata table:\n"
        "\n"
        "| Field | Value |\n"
        "|-------|--------|\n"
        f"| Project | {ctx.project} |\n"
        f"| Task ID | {ctx.current_task_id} |\n"
        f"| Based on version | {ctx.current_version} |\n"
        f"| Author | {label} |\n"
        "\n"
        "Do not include API keys, tokens, or other credentials.\n"
    )
    return scrub_outbound(instructions + "\n" + body, secrets)


def format_dry_run(
    *,
    provider: str,
    model: str,
    would_send: bool,
    max_tokens: int,
    timeout: float,
    method: str,
    url: str,
    headers: dict[str, str],
    body_text: str,
    notes: list[str],
) -> str:
    lines = [
        (
            f"dry-run provider={provider} model={model} "
            f"would_send={'yes' if would_send else 'no'} "
            f"max_tokens={max_tokens} timeout_s={timeout:g}"
        )
    ]
    for note in notes:
        if note:
            lines.append(f"note: {note}")
    if not would_send:
        lines.append(
            "note: a live send would skip this call and write a manual "
            "awaiting_execution packet."
        )
    lines.append(f"{method} {url}")
    for key, value in headers.items():
        lines.append(f"{key}: {value}")
    lines.append("--- body ---")
    lines.append(body_text)
    lines.append("--- end ---")
    return "\n".join(lines) + "\n"


def _result_is_importable(text: str) -> bool:
    try:
        raw = parse_result_markdown(text)
    except Exception:
        return False
    if raw.get("changes") or raw.get("verification_evidence") or raw.get("next_action"):
        return True
    bodies = raw.get("section_bodies") or {}
    return bool(bodies.get("changes"))


def _unwrap_fence(text: str) -> str:
    lines = text.strip().split("\n")
    if len(lines) >= 2 and _FENCE_OPEN.match(lines[0]) and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip() + "\n"
    return text


def reply_to_markdown(
    reply: str,
    ctx: ProjectContext,
    worker: str,
    secrets: list[str],
) -> str:
    """Turn a model reply into Result markdown. Preserves a non-conforming reply."""
    cleaned = scrub_outbound(reply or "", secrets)
    unwrapped = _unwrap_fence(cleaned)
    if _result_is_importable(unwrapped):
        return unwrapped if unwrapped.endswith("\n") else unwrapped + "\n"
    if _result_is_importable(cleaned):
        return cleaned if cleaned.endswith("\n") else cleaned + "\n"
    label = _WORKER_LABELS[worker]
    # Fence the raw reply so headings inside it do not split the wrapper.
    fenced = cleaned.strip()
    return (
        f"# Result — {ctx.current_task_id}\n"
        "\n"
        "| Field | Value |\n"
        "|-------|--------|\n"
        f"| Project | {ctx.project} |\n"
        f"| Task ID | {ctx.current_task_id} |\n"
        f"| Based on version | {ctx.current_version} |\n"
        f"| Author | {label} |\n"
        "\n"
        "## Changes\n"
        "Live reply was not in the official Result format. Full text:\n"
        "\n"
        "```text\n"
        f"{fenced}\n"
        "```\n"
        "\n"
        "## Verification evidence\n"
        "\n"
        "## Blockers\n"
        "- Live reply was not in the official Result format; the full text is preserved under Changes.\n"
        "\n"
        "## Next action\n"
        "Review the preserved reply and continue the manual loop if needed.\n"
    )


def _fallback(
    ctx: ProjectContext,
    worker: str,
    *,
    reason: str,
    error_class: str,
    error_message: str,
    secrets: list[str],
    out_dir: Path | None,
    provider: str,
    model: str,
    note: str = "",
) -> SendOutcome:
    safe_message = scrub_outbound(error_message, secrets)
    safe_class = scrub_outbound(error_class, secrets) or "live_call_failed"
    try:
        result = create_manual_packet(
            ctx,
            worker,
            reason="failed" if reason == "failed" else "unavailable",
            error_class=safe_class,
            error_message=safe_message,
            out_dir=out_dir,
        )
    except Exception as exc:
        # Packet writer failed. Keep the in-memory context if we can.
        try:
            store.save_context(ctx)
        except Exception:
            pass
        raise ValueError(scrub_outbound(str(exc), secrets)) from None
    store.save_context(ctx)
    return SendOutcome(
        exit_code=3,
        fell_back=True,
        dry_run=False,
        would_send=False,
        result=result,
        provider=provider,
        model=model,
        note=note or safe_message,
    )


def _write_reply(ctx: ProjectContext, worker: str, markdown: str) -> Path:
    folder = store.project_dir(ctx.project) / "results"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = utc_now_iso().replace(":", "").replace("-", "")
    path = folder / f"{ctx.current_task_id}-{worker}-live-{stamp}.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def send_hop(
    ctx: ProjectContext,
    worker: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    dry_run: bool = False,
    max_tokens: int | None = None,
    timeout: float | None = None,
    out_dir: Path | None = None,
) -> SendOutcome:
    """Run one hop. Dry-run prints the request and writes nothing.

    On a missing key/endpoint or a failed call, writes the manual packet and
    saves context. Does not raise for transport failures.
    """
    worker_l = (worker or "").strip().lower()
    if worker_l not in LIVE_WORKERS:
        raise ValueError("worker must be claude, grok, glow, or chatgpt")

    provider_name = normalize_provider(provider or default_provider_for(worker_l))
    adapter = make_adapter(
        provider_name,
        model=model,
        base_url=base_url,
        api_key=api_key,
    )
    secrets = known_secrets([adapter.api_key] if adapter.api_key else [])
    tokens, token_note = resolve_max_tokens(
        max_tokens, env_raw=os.environ.get("CB_MAX_TOKENS")
    )
    timeout_s, timeout_note = resolve_timeout(
        timeout, env_raw=os.environ.get("CB_TIMEOUT")
    )
    notes = [n for n in (token_note, timeout_note) if n]

    prompt = build_worker_prompt(ctx, worker_l, secrets)
    prepared = adapter.prepare(prompt, max_tokens=tokens)
    prepared.secrets = secrets
    unavailable = adapter.unavailable_reason()
    would_send = unavailable is None

    if dry_run:
        if unavailable:
            notes.append(unavailable)
        public = prepared.public_headers()
        # Same header set post_json would send. Secret values stay redacted.
        for key, value in finalize_headers(public).items():
            public.setdefault(key, value)
        preview = format_dry_run(
            provider=adapter.name,
            model=adapter.model,
            would_send=would_send,
            max_tokens=tokens,
            timeout=timeout_s,
            method=prepared.method,
            url=redact_secrets(prepared.url, secrets),
            headers=public,
            body_text=prepared.body_text(),
            notes=[scrub_outbound(n, secrets) for n in notes],
        )
        # Exact-key pass over the whole preview. Body was already scrubbed
        # before it was placed in the payload, so this does not rewrite it
        # unless a secret survived into the text.
        preview = redact_secrets(preview, secrets)
        return SendOutcome(
            exit_code=0,
            fell_back=False,
            dry_run=True,
            would_send=would_send,
            preview=preview,
            provider=adapter.name,
            model=adapter.model,
            note=unavailable or "",
        )

    # Drop known keys from the project before any packet, result, or save.
    # Rebuild the prompt so the outbound text matches that redacted context.
    redact_context(ctx, secrets)
    prompt = build_worker_prompt(ctx, worker_l, secrets)

    if unavailable:
        return _fallback(
            ctx,
            worker_l,
            reason="unavailable",
            error_class="connection_unavailable",
            error_message=unavailable,
            secrets=secrets,
            out_dir=out_dir,
            provider=adapter.name,
            model=adapter.model,
            note=unavailable,
        )

    try:
        reply = adapter.invoke(prompt, max_tokens=tokens, timeout=timeout_s)
    except AdapterNotConfigured as exc:
        return _fallback(
            ctx,
            worker_l,
            reason="unavailable",
            error_class="connection_unavailable",
            error_message=str(exc),
            secrets=secrets,
            out_dir=out_dir,
            provider=adapter.name,
            model=adapter.model,
        )
    except LiveCallFailed as exc:
        return _fallback(
            ctx,
            worker_l,
            reason="failed",
            error_class=exc.error_class or "live_call_failed",
            error_message=str(exc),
            secrets=secrets,
            out_dir=out_dir,
            provider=adapter.name,
            model=adapter.model,
        )
    except Exception as exc:
        return _fallback(
            ctx,
            worker_l,
            reason="failed",
            error_class="live_call_failed",
            error_message=f"Live call failed: {type(exc).__name__}: {exc}",
            secrets=secrets,
            out_dir=out_dir,
            provider=adapter.name,
            model=adapter.model,
        )

    reply = scrub_outbound(reply, secrets)
    if not reply.strip():
        return _fallback(
            ctx,
            worker_l,
            reason="failed",
            error_class="bad_response",
            error_message="Provider returned an empty reply.",
            secrets=secrets,
            out_dir=out_dir,
            provider=adapter.name,
            model=adapter.model,
        )

    markdown = reply_to_markdown(reply, ctx, worker_l, secrets)
    markdown = scrub_outbound(markdown, secrets)
    try:
        result_path = _write_reply(ctx, worker_l, markdown)
    except OSError as exc:
        return _fallback(
            ctx,
            worker_l,
            reason="failed",
            error_class="live_call_failed",
            error_message=f"Could not save the live reply: {exc}",
            secrets=secrets,
            out_dir=out_dir,
            provider=adapter.name,
            model=adapter.model,
        )

    try:
        record = load_result(result_path)
    except ResultImportError as exc:
        return _fallback(
            ctx,
            worker_l,
            reason="failed",
            error_class="bad_response",
            error_message=(
                f"Saved live reply at {result_path} but it is not a Result: {exc}"
            ),
            secrets=secrets,
            out_dir=out_dir,
            provider=adapter.name,
            model=adapter.model,
        )

    if not record.author:
        record.author = _WORKER_LABELS[worker_l]
    if not record.handoff_id:
        record.handoff_id = ctx.current_task_id or ""
    if not record.based_on_version:
        record.based_on_version = ctx.current_version
    if not record.project:
        record.project = ctx.project

    try:
        ctx, _flags = apply_result(ctx, record)
        store.save_context(ctx)
    except Exception as exc:
        return _fallback(
            ctx,
            worker_l,
            reason="failed",
            error_class="live_call_failed",
            error_message=(
                f"Saved live reply at {result_path} but import failed: {exc}"
            ),
            secrets=secrets,
            out_dir=out_dir,
            provider=adapter.name,
            model=adapter.model,
        )

    glow_md = glow_json = None
    note = ""
    try:
        md_path, json_path, _pack = write_glow_return_pack(ctx, record)
        glow_md = str(md_path)
        glow_json = str(json_path)
    except Exception as exc:
        # Result is already in context. Do not fall back and double-flag the hop.
        note = scrub_outbound(
            f"Result imported but Glow return pack failed: {exc}",
            secrets,
        )

    message = (
        f"Live hop complete via {adapter.name} ({adapter.model}). "
        "Result imported and Glow return pack written."
    )
    if note:
        message = note
    return SendOutcome(
        exit_code=0,
        fell_back=False,
        dry_run=False,
        would_send=True,
        result=AdapterResult(
            worker=worker_l,
            status=ConnectionStatus.SUCCESS,
            task_id=ctx.current_task_id or "",
            packet_path=str(result_path),
            message=message,
            details={
                "provider": adapter.name,
                "model": adapter.model,
                "result_path": str(result_path),
                "glow_md": glow_md,
                "glow_json": glow_json,
            },
        ),
        result_path=str(result_path),
        glow_md=glow_md,
        glow_json=glow_json,
        provider=adapter.name,
        model=adapter.model,
        note=note,
    )
