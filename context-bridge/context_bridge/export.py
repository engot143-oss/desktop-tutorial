"""Recipient-specific handoff export (Markdown + JSON)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .models import AssignedTask, GlowPlan, HandoffRecord, ProjectContext
from . import store
from .scrub import scrub_obj, scrub_text


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
        flags=list(ctx.flags),
        credentials_included=False,
    )


def _emit_section_body(raw: str | None, fallback_lines: list[str]) -> list[str]:
    """Emit scrubbed raw body (fidelity) or structured fallback lines."""
    if raw is not None:
        # Preserve surrounding whitespace; scrub secrets inside
        return [scrub_text(raw)]
    return fallback_lines


def render_markdown(h: HandoffRecord) -> str:
    plan = h.glow_plan
    raw = plan.raw_sections or {}

    # CB-004: scrub ALL metadata surfaces (project name, source, repo, etc.)
    project = scrub_text(h.project)
    handoff_id = scrub_text(h.handoff_id)
    version = scrub_text(h.version)
    recipient = scrub_text(h.recipient)
    source = scrub_text(h.source)
    repo = scrub_text(h.repo_path) if h.repo_path else "standalone"

    header = "\n".join(
        [
            f"# Handoff {handoff_id} — {project} (for {recipient})",
            "",
            "| Field | Value |",
            "|-------|--------|",
            f"| Project | {project} |",
            f"| Task ID | {handoff_id} |",
            f"| Version | {version} |",
            f"| Recipient | {recipient} |",
            f"| Date | {h.date} |",
            f"| Source | {source} |",
            f"| Repo / path | {repo} |",
            "| Credentials | none — keep out of all exports |",
            "",
            "## Glow plan (preserved)",
            "",
        ]
    )

    # Concatenate four sections so raw body trailing newlines are not altered by join
    section_specs = [
        ("Goal", "goal"),
        ("Constraints", "constraints"),
        ("Open questions", "open_questions"),
        ("Who gets what next", "who_gets_what_next"),
    ]
    glow = ""
    for title, key in section_specs:
        glow += f"### {title}\n"
        if key in raw:
            body = scrub_text(raw[key])
            glow += body
            # Always end the section with a newline before the next heading so a
            # trailing blank line stored in raw (join of a final "" line) survives
            # re-import line-splitting (CB-004 fidelity).
            glow += "\n"
        elif key == "goal":
            glow += scrub_text(plan.goal).rstrip("\n") + "\n"
        elif key == "constraints":
            if plan.constraints:
                for c in plan.constraints:
                    glow += f"- {scrub_text(c)}\n"
            else:
                glow += "- (none)\n"
        elif key == "open_questions":
            if plan.open_questions:
                for q in plan.open_questions:
                    glow += f"- {scrub_text(q)}\n"
            else:
                glow += "- None blocking.\n"
        else:  # who
            if plan.who_gets_what_next:
                for name, action in plan.who_gets_what_next.items():
                    glow += f"- **{scrub_text(name)}:** {scrub_text(action)}\n"
            else:
                glow += "- (none)\n"

    rest_lines: list[str] = ["", "## Decisions"]
    for d in h.decisions:
        rest_lines.append(f"- {scrub_text(d)}")
    if not h.decisions:
        rest_lines.append("- (none recorded)")

    rest_lines.extend(["", "## Assumptions"])
    for a in h.assumptions:
        rest_lines.append(f"- {scrub_text(a)}")
    if not h.assumptions:
        rest_lines.append("- (none recorded)")

    rest_lines.extend(["", "## Assigned tasks"])
    for t in h.assigned_tasks:
        rest_lines.append("")
        rest_lines.append(f"### {scrub_text(t.assignee)}")
        for i, task in enumerate(t.tasks, 1):
            rest_lines.append(f"{i}. {scrub_text(task)}")
        if t.completion_criteria:
            rest_lines.append("")
            rest_lines.append(
                f"**Completion criteria:** {scrub_text(t.completion_criteria)}"
            )
        if t.blocked_until:
            rest_lines.append(f"**Blocked until:** {scrub_text(t.blocked_until)}")

    rest_lines.extend(["", "## Open flags"])
    if h.flags:
        for f in h.flags:
            ftype = f.get("type", "flag")
            msg = f.get("message", "")
            rest_lines.append(f"- **[{ftype}]** {scrub_text(str(msg))}")
    else:
        rest_lines.append("- (none)")

    rest_lines.extend(
        [
            "",
            "## Next action",
            scrub_text(h.next_action or "(see Who gets what next)"),
            "",
        ]
    )
    return header + glow + "\n".join(rest_lines)



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
    # JSON path uses scrub_obj via store.write_json (all string fields)
    store.write_json(json_path, scrub_obj(h.to_dict(), root=True))
    handoffs = store.project_dir(ctx.project) / "handoffs"
    store.write_json(handoffs / f"{base}.json", scrub_obj(h.to_dict(), root=True))
    (handoffs / f"{base}.md").write_text(render_markdown(h), encoding="utf-8")
    return md_path, json_path, h
