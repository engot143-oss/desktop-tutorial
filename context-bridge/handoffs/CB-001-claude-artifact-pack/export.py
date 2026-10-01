"""Recipient-specific handoff export (Markdown + JSON)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .models import AssignedTask, GlowPlan, HandoffRecord, ProjectContext
from . import store


def _recipient_tasks(ctx: ProjectContext, recipient: str) -> list[AssignedTask]:
    """Prefer tasks matching recipient; fall back to all."""
    key = recipient.strip().lower()
    matched = [
        t
        for t in ctx.assigned_tasks
        if key in t.assignee.lower() or t.assignee.lower() in key
    ]
    return matched if matched else list(ctx.assigned_tasks)


def _next_action_for(ctx: ProjectContext, recipient: str) -> str:
    who = (ctx.glow_plan.who_gets_what_next if ctx.glow_plan else {}) or {}
    for name, action in who.items():
        if recipient.lower() in name.lower() or name.lower() in recipient.lower():
            return action
    return ctx.glow_plan.goal if ctx.glow_plan else ""


def build_handoff(ctx: ProjectContext, recipient: str, source: str = "Context Bridge") -> HandoffRecord:
    if not ctx.glow_plan:
        raise ValueError("Project has no Glow plan. Import a plan first.")
    if not ctx.current_task_id:
        raise ValueError("Project has no task ID. Set one on import or via --task-id.")

    return HandoffRecord(
        handoff_id=ctx.current_task_id,
        project=ctx.project,
        version=ctx.current_version,
        recipient=recipient,
        date=date.today().isoformat(),
        source=source,
        repo_path=ctx.repo_path,
        glow_plan=ctx.glow_plan,
        decisions=list(ctx.decisions),
        assumptions=list(ctx.assumptions),
        assigned_tasks=_recipient_tasks(ctx, recipient),
        next_action=_next_action_for(ctx, recipient),
        credentials_included=False,
    )


def render_markdown(h: HandoffRecord) -> str:
    plan = h.glow_plan
    lines: list[str] = [
        f"# Handoff {h.handoff_id} — {h.project} (for {h.recipient})",
        "",
        "| Field | Value |",
        "|-------|--------|",
        f"| Project | {h.project} |",
        f"| Task ID | {h.handoff_id} |",
        f"| Version | {h.version} |",
        f"| Recipient | {h.recipient} |",
        f"| Date | {h.date} |",
        f"| Source | {h.source} |",
        f"| Repo / path | {h.repo_path or 'standalone'} |",
        "| Credentials | none — keep out of all exports |",
        "",
        "## Glow plan (preserved)",
        "",
        "### Goal",
        plan.goal,
        "",
        "### Constraints",
    ]
    for c in plan.constraints:
        lines.append(f"- {c}")
    if not plan.constraints:
        lines.append("- (none)")
    lines.extend(["", "### Open questions"])
    if plan.open_questions:
        for q in plan.open_questions:
            lines.append(f"- {q}")
    else:
        lines.append("- None blocking.")
    lines.extend(["", "### Who gets what next"])
    for name, action in plan.who_gets_what_next.items():
        lines.append(f"- **{name}:** {action}")
    if not plan.who_gets_what_next:
        lines.append("- (none)")

    lines.extend(["", "## Decisions"])
    for d in h.decisions:
        lines.append(f"- {d}")
    if not h.decisions:
        lines.append("- (none recorded)")

    lines.extend(["", "## Assumptions"])
    for a in h.assumptions:
        lines.append(f"- {a}")
    if not h.assumptions:
        lines.append("- (none recorded)")

    lines.extend(["", "## Assigned tasks"])
    for t in h.assigned_tasks:
        lines.append(f"")
        lines.append(f"### {t.assignee}")
        for i, task in enumerate(t.tasks, 1):
            lines.append(f"{i}. {task}")
        if t.completion_criteria:
            lines.append("")
            lines.append(f"**Completion criteria:** {t.completion_criteria}")
        if t.blocked_until:
            lines.append(f"**Blocked until:** {t.blocked_until}")

    lines.extend(["", "## Next action", h.next_action or "(see Who gets what next)", ""])
    return "\n".join(lines)


def export_handoff(
    ctx: ProjectContext,
    recipient: str,
    out_dir: Path | None = None,
    source: str = "Context Bridge",
) -> tuple[Path, Path, HandoffRecord]:
    h = build_handoff(ctx, recipient, source=source)
    if out_dir is None:
        out_dir = store.project_dir(ctx.project) / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = recipient.strip().lower().replace(" ", "-")
    base = f"{h.handoff_id}-{slug}-v{h.version}"
    md_path = out_dir / f"{base}.md"
    json_path = out_dir / f"{base}.json"
    md_path.write_text(render_markdown(h), encoding="utf-8")
    store.write_json(json_path, h.to_dict())
    # Also stash under handoffs/
    handoffs = store.project_dir(ctx.project) / "handoffs"
    store.write_json(handoffs / f"{base}.json", h.to_dict())
    (handoffs / f"{base}.md").write_text(render_markdown(h), encoding="utf-8")
    return md_path, json_path, h
