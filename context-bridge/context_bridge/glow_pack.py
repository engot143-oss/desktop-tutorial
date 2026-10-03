"""Slice B — Glow return pack after result import."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from . import store
from .models import ProjectContext, ResultRecord, utc_now_iso
from .scrub import scrub_obj, scrub_text


def build_glow_return_pack(
    ctx: ProjectContext,
    result: ResultRecord | None = None,
    *,
    findings: list[str] | None = None,
) -> dict[str, Any]:
    """
    Glow-facing summary: findings, evidence, blockers, next action,
    decisions, task ID, based-on-version, all open flags.
    CB-007: also carries scrubbed section_bodies / raw_markdown.
    """
    flags = list(ctx.flags)
    changes = list(result.changes) if result else []
    evidence = list(result.verification_evidence) if result else []
    blockers = list(result.blockers) if result else []
    next_action = result.next_action if result else ""
    task_id = (result.handoff_id if result else None) or ctx.current_task_id
    based_on = (result.based_on_version if result else "") or ""

    # Explicit missing-evidence report
    if result is not None and not evidence:
        flags = list(flags) + [
            {
                "type": "missing_evidence",
                "at": utc_now_iso(),
                "message": "Result has no verification evidence.",
                "handoff_id": task_id,
                "author": result.author if result else "",
            }
        ]

    section_bodies: dict[str, str] = {}
    raw_markdown = ""
    if result is not None:
        section_bodies = {
            str(k): scrub_text(str(v))
            for k, v in (result.section_bodies or {}).items()
        }
        raw_markdown = scrub_text(result.raw_markdown or "")

    pack = {
        "pack_type": "glow_return",
        "project": ctx.project,
        "task_id": task_id,
        "based_on_version": based_on,
        "project_version": ctx.current_version,
        "date": date.today().isoformat(),
        "repo_path": ctx.repo_path,
        "findings": findings if findings is not None else changes,
        "verification_evidence": evidence,
        "blockers": blockers,
        "next_action": next_action,
        "decisions": list(ctx.decisions),
        "assumptions": list(ctx.assumptions),
        "section_bodies": section_bodies,
        "raw_markdown": raw_markdown,
        "open_flags": flags,
        "flag_summary": {
            "conflict": sum(1 for f in flags if f.get("type") == "conflict"),
            "outdated": sum(1 for f in flags if f.get("type") == "outdated"),
            "missing_evidence": sum(
                1 for f in flags if f.get("type") == "missing_evidence"
            ),
            "failed_call": sum(1 for f in flags if f.get("type") == "failed_call"),
            "connection_unavailable": sum(
                1 for f in flags if f.get("type") == "connection_unavailable"
            ),
            "other": sum(
                1
                for f in flags
                if f.get("type")
                not in (
                    "conflict",
                    "outdated",
                    "missing_evidence",
                    "failed_call",
                    "connection_unavailable",
                )
            ),
        },
        "hierarchy": "Eric → Glow → Grok Bot (execution) → Claude (coding) / Grok (explore)",
        "credentials_included": False,
    }
    return scrub_obj(pack, root=True)


def render_glow_return_markdown(pack: dict[str, Any]) -> str:
    lines = [
        f"# Glow return pack — {pack.get('task_id') or 'task'} ({pack.get('project')})",
        "",
        "| Field | Value |",
        "|-------|--------|",
        f"| Project | {pack.get('project')} |",
        f"| Task ID | {pack.get('task_id')} |",
        f"| Based on version | {pack.get('based_on_version') or '(none)'} |",
        f"| Project version | {pack.get('project_version')} |",
        f"| Date | {pack.get('date')} |",
        f"| Repo / path | {pack.get('repo_path') or 'standalone'} |",
        "| Credentials | scrubbed — none included |",
        "",
        "## Findings",
    ]
    findings = pack.get("findings") or []
    if findings:
        for f in findings:
            lines.append(f"- {scrub_text(str(f))}")
    else:
        lines.append("- (none)")

    # CB-007: full Changes body (tables, nested headings, proposed wording)
    lines.extend(["", "## Full Changes (preserved)", ""])
    sb = pack.get("section_bodies") or {}
    full_changes = sb.get("changes") if isinstance(sb, dict) else None
    if full_changes:
        lines.append(scrub_text(str(full_changes)))
    elif findings:
        # Compat: old results without section_bodies
        for f in findings:
            lines.append(f"- {scrub_text(str(f))}")
    else:
        lines.append("(none)")

    lines.extend(["", "## Verification evidence"])
    ev = pack.get("verification_evidence") or []
    if ev:
        for e in ev:
            lines.append(f"- {scrub_text(str(e))}")
    else:
        lines.append("- (missing — see open flags)")

    lines.extend(["", "## Blockers"])
    blockers = pack.get("blockers") or []
    if blockers:
        for b in blockers:
            lines.append(f"- {scrub_text(str(b))}")
    else:
        lines.append("- None.")

    lines.extend(["", "## Next action", scrub_text(str(pack.get("next_action") or "(none)")), ""])

    lines.extend(["", "## Decisions (preserved)"])
    for d in pack.get("decisions") or []:
        lines.append(f"- {scrub_text(str(d))}")
    if not pack.get("decisions"):
        lines.append("- (none)")

    lines.extend(["", "## Open flags"])
    flags = pack.get("open_flags") or []
    if flags:
        for f in flags:
            lines.append(
                f"- **[{scrub_text(str(f.get('type', 'flag')))}]** {scrub_text(str(f.get('message', '')))}"
            )
    else:
        lines.append("- (none)")

    summary = pack.get("flag_summary") or {}
    lines.extend(
        [
            "",
            "## Flag summary",
            f"- conflict: {summary.get('conflict', 0)}",
            f"- outdated: {summary.get('outdated', 0)}",
            f"- missing_evidence: {summary.get('missing_evidence', 0)}",
            f"- failed_call: {summary.get('failed_call', 0)}",
            f"- connection_unavailable: {summary.get('connection_unavailable', 0)}",
            "",
            f"_Hierarchy: {pack.get('hierarchy')}_",
            "",
        ]
    )
    return "\n".join(lines)


def write_glow_return_pack(
    ctx: ProjectContext,
    result: ResultRecord | None = None,
    out_dir: Path | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    pack = build_glow_return_pack(ctx, result)
    if out_dir is None:
        out_dir = store.project_dir(ctx.project) / "glow_returns"
    out_dir.mkdir(parents=True, exist_ok=True)
    tid = pack.get("task_id") or "task"
    stamp = utc_now_iso().replace(":", "").replace("-", "")
    base = f"{tid}-glow-return-{stamp}"
    md_path = out_dir / f"{base}.md"
    json_path = out_dir / f"{base}.json"
    md_path.write_text(render_glow_return_markdown(pack), encoding="utf-8")
    store.write_json(json_path, pack)
    # Convenience latest pointers
    (out_dir / "latest.md").write_text(render_glow_return_markdown(pack), encoding="utf-8")
    store.write_json(out_dir / "latest.json", pack)
    return md_path, json_path, pack
