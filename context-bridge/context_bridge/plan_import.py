"""Parse Glow four-section Markdown plans into structured data."""

from __future__ import annotations

import re
from pathlib import Path

from .models import AssignedTask, GlowPlan, ProjectContext, utc_now_iso

# Literal titles only (exact characters — CB-005). Keys are section ids.
EXACT_TITLES: dict[str, str] = {
    "Goal": "goal",
    "Constraints": "constraints",
    "Open questions": "open_questions",
    "Who gets what next": "who_gets_what_next",
}

REQUIRED_SECTIONS = ("goal", "constraints", "open_questions", "who_gets_what_next")
REQUIRED_TITLE_LABELS = (
    "Goal",
    "Constraints",
    "Open questions",
    "Who gets what next",
)

# Companion / chrome headings that end a Glow section — only at structural
# level # or ## (not nested #### inside a body).
STOP_HEADINGS = {
    "decisions",
    "assumptions",
    "assigned tasks",
    "next action",
    "changes",
    "verification evidence",
    "blockers",
    "new decisions",
    "new assumptions",
    "context",
    "what to verify",
    "completion criteria for your review",
    "open flags",
    "flag summary",
    "glow plan (preserved)",
    "glow plan",
}


class PlanImportError(ValueError):
    pass


def _detect_line_ending(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    return "\n"


def _split_lines(text: str, ending: str) -> list[str]:
    """Split text on ending without converting CRLF→LF in body content."""
    if ending == "\r\n":
        # Also handle any lone \n defensively by normalizing only for split of
        # mixed docs: prefer preserving CRLF segments.
        return text.split("\r\n")
    return text.split("\n")


def _normalize_heading_for_stop(text: str) -> str:
    """Lowercase normalize for companion stop matching only."""
    t = text.strip().lower()
    t = re.sub(r"^#+\s*", "", t)
    t = re.sub(r"^\*+\s*|\s*\*+$", "", t)
    t = re.sub(r"^_+\s*|\s*_+$", "", t)
    return t.strip()


def _exact_glow_key(title_raw: str) -> str | None:
    """
    Return section key only for literal canonical titles.
    Rejects lowercase, bold wrappers, altered names (CB-005).
    """
    # Exact match after outer whitespace only — no case fold, no bold strip
    return EXACT_TITLES.get(title_raw.strip())


def _split_sections(markdown: str) -> tuple[dict[str, str], str, list[str], str]:
    """
    Split markdown on Glow four-section headings.

    Enforces exact literal titles, exact order, no duplicates.
    Preserves CRLF and section body whitespace.
    Nested headings deeper than ## (e.g. #### Decisions) stay in the body.
    Returns (sections, preamble, ordered_keys, line_ending).
    """
    ending = _detect_line_ending(markdown)
    lines = _split_lines(markdown, ending)
    sections: dict[str, list[str]] = {}
    order: list[str] = []
    current: str | None = None
    preamble: list[str] = []
    in_glow = False

    # Capture heading level (1-4) and exact title text
    heading_re = re.compile(r"^(#{1,4})\s+(.*?)\s*$")

    for line in lines:
        # For heading match, also allow CRLF already stripped by split
        m = heading_re.match(line)
        if m:
            level = len(m.group(1))
            title_raw = m.group(2)
            mapped = _exact_glow_key(title_raw)
            if mapped is not None:
                if mapped in sections:
                    raise PlanImportError(
                        f"Duplicate Glow section heading: '{title_raw.strip()}'. "
                        "Each of Goal / Constraints / Open questions / Who gets what next "
                        "may appear exactly once."
                    )
                current = mapped
                in_glow = True
                sections[current] = []
                order.append(current)
                continue

            # Companion stop only at document structural levels # or ##
            stop_norm = _normalize_heading_for_stop(title_raw)
            stop_key = stop_norm.split("—")[0].split("(")[0].strip()
            is_stop = stop_key in STOP_HEADINGS or any(
                stop_key.startswith(s) for s in STOP_HEADINGS
            )
            if is_stop and level <= 2:
                current = None
                in_glow = False
                continue

            # Nested heading (###/####) or non-stop: keep in body for fidelity
            if current is not None:
                sections[current].append(line)
                continue
            if not in_glow:
                preamble.append(line)
            continue

        if current is None:
            if not in_glow:
                preamble.append(line)
        else:
            sections[current].append(line)

    body_map = {k: ending.join(v) for k, v in sections.items()}
    return body_map, ending.join(preamble), order, ending


def _parse_bullet_list(body: str, *, join_continuations: bool = False) -> list[str]:
    """Parse bullet/numbered lists without joining continuations by default."""
    items: list[str] = []
    # Normalize only for line iteration of structured view
    for line in body.replace("\r\n", "\n").split("\n"):
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^[-*+]\s+(.*)$", s)
        if m:
            items.append(m.group(1))
            continue
        if re.match(r"^\d+\.\s+", s):
            items.append(re.sub(r"^\d+\.\s+", "", s))
            continue
        if re.match(r"(?i)^\*\*(completion criteria|blocked until)", s):
            items.append(s)
            continue
        if join_continuations and items:
            items[-1] = items[-1] + " " + s
        else:
            items.append(s)
    return items


def _parse_who_gets_what(body: str) -> dict[str, str]:
    """Parse '- **Name:** task' or '- Name: task' lines."""
    result: dict[str, str] = {}
    for line in body.replace("\r\n", "\n").split("\n"):
        s = line.strip()
        if not s:
            continue
        s = re.sub(r"^[-*+]\s+", "", s)
        m = re.match(r"^\*\*([^*]+?):\*\*\s*(.+)$", s)
        if not m:
            m = re.match(r"^\*\*([^*]+?)\*\*\s*[:—-]\s*(.+)$", s)
        if not m:
            m = re.match(r"^([^:]+):\s*(.+)$", s)
        if m:
            name = m.group(1).strip().strip("*").strip()
            result[name] = m.group(2).strip()
    return result


def _extract_meta(preamble: str, markdown: str) -> dict[str, str | None]:
    meta: dict[str, str | None] = {
        "project": None,
        "task_id": None,
        "version": None,
        "repo_path": None,
        "source": None,
    }
    for m in re.finditer(
        r"\|\s*(Project|Task ID|Version|Repo\s*/\s*path|Source)\s*\|\s*([^|]+)\|",
        markdown,
        re.IGNORECASE,
    ):
        field = m.group(1).strip().lower()
        value = m.group(2).strip()
        if field == "project":
            meta["project"] = value
        elif field == "task id":
            meta["task_id"] = value
        elif field == "version":
            meta["version"] = value
        elif "repo" in field:
            low = value.lower()
            meta["repo_path"] = (
                None
                if low in ("standalone", "null", "n/a", "-")
                or low.startswith("standalone")
                else value
            )
        elif field == "source":
            meta["source"] = value
    return meta


def _parse_assignee_block(title: str, body: str) -> AssignedTask:
    assignee = re.split(r"\s*[—-]\s*", title.strip())[0].strip()
    criteria = ""
    blocked = None
    kept_lines: list[str] = []
    for line in body.replace("\r\n", "\n").split("\n"):
        s = line.strip()
        cm = re.match(r"(?i)^\*\*completion criteria:?\*\*\s*(.*)$", s)
        if not cm:
            cm = re.match(r"(?i)^completion criteria:?\s*(.*)$", s)
        if cm:
            if cm.group(1).strip():
                criteria = cm.group(1).strip()
            continue
        bm = re.match(r"(?i)^\*\*blocked until:?\*\*\s*(.*)$", s)
        if not bm:
            bm = re.match(r"(?i)^blocked until:?\s*(.*)$", s)
        if bm:
            blocked = bm.group(1).strip() or None
            continue
        kept_lines.append(line)

    tasks_raw = _parse_bullet_list("\n".join(kept_lines), join_continuations=False)
    clean_tasks: list[str] = []
    for t in tasks_raw:
        parts = re.split(r"(?i)\s*\*\*completion criteria:?\*\*\s*", t, maxsplit=1)
        task_text = parts[0].strip()
        if len(parts) > 1 and parts[1].strip():
            criteria = parts[1].strip()
        parts2 = re.split(r"(?i)\s+completion criteria:\s*", task_text, maxsplit=1)
        task_text = parts2[0].strip()
        if len(parts2) > 1 and parts2[1].strip() and not criteria:
            criteria = parts2[1].strip()
        if not task_text:
            continue
        if task_text.lower().startswith("completion criteria"):
            criteria = re.sub(r"(?i)^completion criteria:?\s*", "", task_text).strip()
            continue
        clean_tasks.append(task_text)

    if not criteria:
        cm = re.search(r"(?im)\*\*completion criteria:?\*\*\s*(.+)", body)
        if cm:
            criteria = cm.group(1).strip()
    if blocked is None:
        bm = re.search(r"(?im)\*\*blocked until:?\*\*\s*(.+)", body)
        if bm:
            blocked = bm.group(1).strip()
    return AssignedTask(
        assignee=assignee,
        tasks=clean_tasks,
        completion_criteria=criteria,
        blocked_until=blocked,
    )


def _extract_extra_lists(markdown: str) -> tuple[list[str], list[str], list[AssignedTask]]:
    decisions: list[str] = []
    assumptions: list[str] = []
    assigned: list[AssignedTask] = []

    # Companion sections at # / ## only
    heading_re = re.compile(r"^(#{1,2})\s+(.+?)\s*$", re.MULTILINE)
    # Work on LF view for companion extract (structured only)
    text = markdown.replace("\r\n", "\n")
    parts = heading_re.split(text)
    i = 1
    while i + 2 < len(parts):
        title = _normalize_heading_for_stop(parts[i + 1])
        body = parts[i + 2]
        if title == "decisions":
            decisions = _parse_bullet_list(body, join_continuations=False)
        elif title == "assumptions":
            assumptions = _parse_bullet_list(body, join_continuations=False)
        elif title.startswith("assigned tasks"):
            sub_re = re.compile(r"^(#{3,4})\s+(.+?)\s*$", re.MULTILINE)
            sub_parts = sub_re.split(body)
            if len(sub_parts) > 1:
                j = 1
                while j + 2 < len(sub_parts):
                    assigned.append(
                        _parse_assignee_block(sub_parts[j + 1], sub_parts[j + 2])
                    )
                    j += 3
            else:
                assigned.append(
                    AssignedTask(
                        assignee="unspecified",
                        tasks=_parse_bullet_list(body, join_continuations=False),
                    )
                )
        i += 3

    return decisions, assumptions, assigned


def parse_glow_plan_markdown(
    markdown: str,
) -> tuple[GlowPlan, dict, list[str], list[str], list[AssignedTask]]:
    """
    Parse Markdown with exactly the four Glow sections in order,
    with literal titles, preserving CRLF and body whitespace.
    """
    sections, preamble, order, ending = _split_sections(markdown)

    if order != list(REQUIRED_SECTIONS):
        got = " → ".join(order) if order else "(none)"
        missing = [s for s in REQUIRED_SECTIONS if s not in sections]
        detail = []
        if missing:
            detail.append(f"missing: {', '.join(missing)}")
        if order and order != list(REQUIRED_SECTIONS) and not missing:
            detail.append(f"wrong order (got {got})")
        raise PlanImportError(
            "Glow plan must include exactly these sections in order, "
            "with literal titles (no lowercase, bold, rename, or duplicates): "
            + " / ".join(REQUIRED_TITLE_LABELS)
            + f". Got: {got}. "
            + ("; ".join(detail) if detail else "")
        )

    raw_sections = {k: sections[k] for k in REQUIRED_SECTIONS}

    goal = raw_sections["goal"]
    constraints = _parse_bullet_list(
        raw_sections["constraints"], join_continuations=False
    )
    open_questions = _parse_bullet_list(
        raw_sections["open_questions"], join_continuations=False
    )
    who = _parse_who_gets_what(raw_sections["who_gets_what_next"])

    plan = GlowPlan(
        goal=goal,
        constraints=constraints,
        open_questions=open_questions,
        who_gets_what_next=who,
        raw_sections=raw_sections,
        line_ending=ending,
    )
    meta = _extract_meta(preamble, markdown)
    decisions, assumptions, assigned = _extract_extra_lists(markdown)
    return plan, meta, decisions, assumptions, assigned


def import_plan_file(
    path: Path,
    ctx: ProjectContext,
    task_id: str | None = None,
    version: str | None = None,
    merge_decisions: bool = True,
) -> ProjectContext:
    """Import a Glow plan file into project context, preserving prior decisions."""
    # Read as binary then decode to preserve CRLF in text
    raw_bytes = path.read_bytes()
    text = raw_bytes.decode("utf-8")
    plan, meta, decisions, assumptions, assigned = parse_glow_plan_markdown(text)

    if ctx.decisions:
        ctx.decision_history.append(
            {
                "at": utc_now_iso(),
                "version": ctx.current_version,
                "decisions": list(ctx.decisions),
                "event": "pre_import_snapshot",
            }
        )

    ctx.glow_plan = plan
    if meta.get("project") and not ctx.project:
        ctx.project = str(meta["project"])
    if meta.get("repo_path") is not None:
        ctx.repo_path = meta["repo_path"]  # type: ignore[assignment]
    if task_id or meta.get("task_id"):
        ctx.current_task_id = task_id or str(meta["task_id"])
    if version or meta.get("version"):
        ctx.current_version = version or str(meta["version"])

    if merge_decisions:
        existing = {d.strip().lower() for d in ctx.decisions}
        for d in decisions:
            if d.strip().lower() not in existing:
                ctx.decisions.append(d)
                existing.add(d.strip().lower())
        existing_a = {a.strip().lower() for a in ctx.assumptions}
        for a in assumptions:
            if a.strip().lower() not in existing_a:
                ctx.assumptions.append(a)
                existing_a.add(a.strip().lower())
    else:
        ctx.decisions = decisions
        ctx.assumptions = assumptions

    if assigned:
        ctx.assigned_tasks = assigned

    ctx.updated_at = utc_now_iso()
    return ctx
