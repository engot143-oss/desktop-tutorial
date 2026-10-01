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


def render_markdown(h: HandoffRecord) -> str:
    """
    Render handoff Markdown.

    CB-005 separator rule: emit `### Title\\n` + body, then exactly one
    newline before the next heading (stable across repeated round-trips).
    Uses plan.line_ending for CRLF documents.
    """
    plan = h.glow_plan
    raw = plan.raw_sections or {}
    nl = plan.line_ending if plan.line_ending in ("\n", "\r\n") else "\n"

    project = scrub_text(h.project)
    handoff_id = scrub_text(h.handoff_id)
    version = scrub_text(h.version)
    recipient = scrub_text(h.recipient)
    source = scrub_text(h.source)
    repo = scrub_text(h.repo_path) if h.repo_path else "standalone"

    header_lines = [
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
    header = nl.join(header_lines) + nl

    section_specs = [
        ("Goal", "goal"),
        ("Constraints", "constraints"),
        ("Open questions", "open_questions"),
        ("Who gets what next", "who_gets_what_next"),
    ]

    glow = ""
    for title, key in section_specs:
        glow += f"### {title}{nl}"
        if key in raw:
            body = scrub_text(raw[key])
            glow += body
            # Always exactly one separator newline before the next heading.
            # Combined with companion sections that do NOT start with a blank
            # line, this is stable across ≥3 round-trips (CB-005).
            glow += nl
        elif key == "goal":
            glow += scrub_text(plan.goal).rstrip("\r\n") + nl
        elif key == "constraints":
            if plan.constraints:
                for c in plan.constraints:
                    glow += f"- {scrub_text(c)}{nl}"
            else:
                glow += f"- (none){nl}"
        elif key == "open_questions":
            if plan.open_questions:
                for q in plan.open_questions:
                    glow += f"- {scrub_text(q)}{nl}"
            else:
                glow += f"- None blocking.{nl}"
        else:
            if plan.who_gets_what_next:
                for name, action in plan.who_gets_what_next.items():
                    glow += f"- **{scrub_text(name)}:** {scrub_text(action)}{nl}"
            else:
                glow += f"- (none){nl}"

    # Companion sections — start directly with ## (no extra blank that would
    # append into the last Glow body on re-import).
    rest: list[str] = ["## Decisions"]
    for d in h.decisions:
        rest.append(f"- {scrub_text(d)}")
    if not h.decisions:
        rest.append("- (none recorded)")

    rest.extend(["", "## Assumptions"])
    for a in h.assumptions:
        rest.append(f"- {scrub_text(a)}")
    if not h.assumptions:
        rest.append("- (none recorded)")

    rest.extend(["", "## Assigned tasks"])
    for t in h.assigned_tasks:
        rest.append("")
        rest.append(f"### {scrub_text(t.assignee)}")
        for i, task in enumerate(t.tasks, 1):
            rest.append(f"{i}. {scrub_text(task)}")
        if t.completion_criteria:
            rest.append("")
            rest.append(
                f"**Completion criteria:** {scrub_text(t.completion_criteria)}"
            )
        if t.blocked_until:
            rest.append(f"**Blocked until:** {scrub_text(t.blocked_until)}")

    rest.extend(["", "## Open flags"])
    if h.flags:
        for f in h.flags:
            ftype = scrub_text(str(f.get("type", "flag")))
            msg = scrub_text(str(f.get("message", "")))
            rest.append(f"- **[{ftype}]** {msg}")
    else:
        rest.append("- (none)")

    rest.extend(
        [
            "",
            "## Next action",
            scrub_text(h.next_action or "(see Who gets what next)"),
            "",
        ]
    )
    return header + glow + nl.join(rest)


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
    md_text = render_markdown(h)
    # Write bytes to preserve CRLF when present
    md_path.write_bytes(md_text.encode("utf-8"))
    store.write_json(json_path, scrub_obj(h.to_dict(), root=True))
    handoffs = store.project_dir(ctx.project) / "handoffs"
    store.write_json(handoffs / f"{base}.json", scrub_obj(h.to_dict(), root=True))
    (handoffs / f"{base}.md").write_bytes(md_text.encode("utf-8"))
    return md_path, json_path, h
