"""Manual paste adapters — produce awaiting_execution packets (no live calls)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .. import store
from ..export import build_handoff, render_markdown
from ..models import ProjectContext, utc_now_iso
from ..scrub import scrub_obj, scrub_text
from .base import AdapterResult, ConnectionStatus


class ManualAdapter:
    """
    v1.1 adapter: never makes a live network call.
    Always writes a credential-scrubbed manual packet marked awaiting_execution.
    Distinguishes:
      - unavailable: no authorized live connection (default / expected path)
      - failed: caller reports an attempted live call that failed (recorded only)
    """

    name = "manual"

    def __init__(self, worker: str):
        w = worker.strip().lower()
        if w not in ("claude", "grok"):
            raise ValueError("worker must be claude or grok")
        self.worker = w

    def dispatch(
        self,
        ctx: ProjectContext,
        *,
        reason: str = "unavailable",
        error_class: str | None = None,
        error_message: str | None = None,
        instructions: str | None = None,
        out_dir: Path | None = None,
    ) -> AdapterResult:
        reason_l = (reason or "unavailable").strip().lower()
        if reason_l in ("failed", "attempted-but-failed", "call_failed"):
            conn = ConnectionStatus.FAILED
            error_class = error_class or "live_call_failed"
            error_message = error_message or (
                "Live call attempted but failed; falling back to manual packet."
            )
        else:
            conn = ConnectionStatus.UNAVAILABLE
            error_class = error_class or "connection_unavailable"
            error_message = error_message or (
                "No authorized live connection; manual paste packet prepared."
            )

        packet_path, packet = write_manual_packet(
            ctx,
            worker=self.worker,
            connection_status=conn,
            error_class=error_class,
            error_message=error_message,
            instructions=instructions,
            out_dir=out_dir,
        )

        # Record flag on context (caller should save)
        flag = {
            "type": (
                "failed_call"
                if conn == ConnectionStatus.FAILED
                else "connection_unavailable"
            ),
            "at": utc_now_iso(),
            "message": (
                f"{self.worker}: {error_class} — {error_message} "
                f"(packet: {packet_path})"
            ),
            "handoff_id": ctx.current_task_id,
            "worker": self.worker,
            "packet_path": str(packet_path),
            "error_class": error_class,
        }
        ctx.flags.append(flag)

        return AdapterResult(
            worker=self.worker,
            status=ConnectionStatus.AWAITING_EXECUTION,
            task_id=ctx.current_task_id or "",
            packet_path=str(packet_path),
            error_class=error_class,
            error_message=error_message,
            message=(
                f"Manual packet ready (awaiting_execution). "
                f"Underlying: {conn.value}. Paste to {self.worker}, then import-result."
            ),
            details={
                "connection": conn.value,
                "packet_status": packet.get("status"),
                "underlying": conn.value,
            },
        )


def write_manual_packet(
    ctx: ProjectContext,
    *,
    worker: str,
    connection_status: ConnectionStatus = ConnectionStatus.UNAVAILABLE,
    error_class: str | None = None,
    error_message: str | None = None,
    instructions: str | None = None,
    out_dir: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Write scrubbed Markdown+JSON packet marked awaiting_execution."""
    if not ctx.glow_plan:
        raise ValueError("Project has no Glow plan. Import a plan first.")
    if not ctx.current_task_id:
        raise ValueError("Project has no task ID.")

    recipient_label = "Claude" if worker == "claude" else "Grok"
    handoff = build_handoff(ctx, recipient_label, source="Context Bridge manual adapter")
    md_body = render_markdown(handoff)

    default_instructions = (
        f"You are the {recipient_label} worker under hierarchy "
        "Eric → Glow → Grok Bot → Claude (coding) / Grok (explore).\n"
        "Execute the assigned work. Return a Result using the official format:\n"
        "Changes / Verification evidence / Blockers / Next action / Decisions.\n"
        "Paste the Result back for `cb import-result`."
    )
    instr = instructions or default_instructions

    packet: dict[str, Any] = {
        "packet_type": "manual_worker_packet",
        "status": "awaiting_execution",
        "connection": connection_status.value,
        "worker": worker,
        "adapter": "manual",
        "project": ctx.project,
        "task_id": ctx.current_task_id,
        "version": ctx.current_version,
        "repo_path": ctx.repo_path,
        "date": date.today().isoformat(),
        "error_class": error_class,
        "error_message": error_message,
        "instructions": instr,
        "decisions": list(ctx.decisions),
        "assumptions": list(ctx.assumptions),
        "open_flags": list(ctx.flags),
        "handoff": handoff.to_dict(),
        "credentials_included": False,
        # Extension point for future live adapters:
        "live_adapter_ready": False,
        "live_adapter_notes": (
            "Live Claude/Grok connections are out of scope until Eric authorizes. "
            "This packet shape is stable for future live adapters to fill."
        ),
    }
    packet = scrub_obj(packet, root=True)

    if out_dir is None:
        out_dir = store.project_dir(ctx.project) / "packets"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_now_iso().replace(":", "").replace("-", "")
    base = f"{ctx.current_task_id}-{worker}-packet-{stamp}"
    json_path = out_dir / f"{base}.json"
    md_path = out_dir / f"{base}.md"

    # CB-005: scrub ALL packet metadata surfaces (project/task/version/error class)
    sp = scrub_text(ctx.project)
    st = scrub_text(ctx.current_task_id or "")
    sv = scrub_text(ctx.current_version)
    sec = scrub_text(error_class or "(n/a)")
    sem = scrub_text(error_message or "")
    md_lines = [
        f"# Manual packet — {st} for {recipient_label}",
        "",
        f"**Status:** `awaiting_execution`",
        f"**Connection:** `{connection_status.value}` "
        f"({'no live link' if connection_status == ConnectionStatus.UNAVAILABLE else 'attempted live call failed'})",
        f"**Worker:** {scrub_text(worker)}",
        f"**Adapter:** manual",
        f"**Project:** {sp}",
        f"**Task ID:** {st}",
        f"**Version:** {sv}",
        f"**Error class:** {sec}",
        f"**Error message:** {sem}",
        "",
        "## Instructions",
        scrub_text(instr),
        "",
        "## Handoff (scrubbed)",
        "",
        md_body,  # already scrubbed by render_markdown
        "",
        "---",
        "After execution, return a Result Markdown and run:",
        f'`cb import-result "{sp}" path/to/result.md '
        f'--task-id {st} --based-on-version {sv}`',
        "",
    ]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    store.write_json(json_path, packet)
    # Prefer returning markdown path as the paste surface
    return md_path, packet


def create_manual_packet(
    ctx: ProjectContext,
    worker: str,
    *,
    reason: str = "unavailable",
    error_class: str | None = None,
    error_message: str | None = None,
    instructions: str | None = None,
    out_dir: Path | None = None,
) -> AdapterResult:
    return ManualAdapter(worker).dispatch(
        ctx,
        reason=reason,
        error_class=error_class,
        error_message=error_message,
        instructions=instructions,
        out_dir=out_dir,
    )
