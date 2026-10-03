"""Import results and flag conflicting / outdated updates."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .models import ProjectContext, ResultRecord, utc_now_iso
from .scrub import scrub_text
from . import store


class ResultImportError(ValueError):
    pass


# Separator when the same official heading appears more than once (CB-007).
_DUP_SECTION_SEP = "\n\n<!-- duplicate official heading -->\n\n"

# Heading line: 1–4 hashes + title (matched only outside fenced code blocks).
_HEADING_LINE_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$")


# Explicit alias allowlist for official Result headings (CB-007 Glow fix).
# Exact match only (case-insensitive). Prefix/startswith matching is forbidden
# so titles like "Blocker examples", "Next actions proposed", or
# "New decision examples" stay inside the current section.
_OFFICIAL_HEADING_ALIASES: dict[str, str] = {
    "changes": "changes",
    "verification evidence": "verification_evidence",
    "blockers": "blockers",
    "blocker": "blockers",
    "next action": "next_action",
    "decisions": "decisions",
    "new decisions": "decisions",
    "decisions added": "decisions",
    "assumptions": "assumptions",
    "new assumptions": "assumptions",
}


def _normalize_heading_title(title: str) -> str:
    """Lowercase + strip; drop trailing punctuation only (keep inner words intact)."""
    t = title.strip().lower()
    return t.rstrip(".:;!?,")


def _official_section_key(title: str) -> str | None:
    """
    Map an official Result heading to a section_bodies key.

    Exact alias allowlist only (case-insensitive). Non-official headings
    (Requirements, Setup, Blocker examples, …) return None so they stay
    inside the current section body.
    """
    return _OFFICIAL_HEADING_ALIASES.get(_normalize_heading_title(title))


# Fence line: 3+ backticks or tildes (CommonMark). Closer needs same char
# and length >= opening length; info string only allowed on openers.
_FENCE_LINE_RE = re.compile(r"^(`{3,}|~{3,})(.*)$")


def _iter_outside_fences(lines: list[str]):
    """
    Yield (index, line) for lines outside fenced code blocks.

    CommonMark-style: track fence character and opening length; a closer must
    use the same character with length >= opening length and no info string.
    """
    in_fence = False
    fence_char: str | None = None
    fence_len: int = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        fence_m = _FENCE_LINE_RE.match(stripped)
        if fence_m:
            marker = fence_m.group(1)
            rest = fence_m.group(2)
            if not in_fence:
                in_fence = True
                fence_char = marker[0]
                fence_len = len(marker)
            elif (
                fence_char is not None
                and marker[0] == fence_char
                and len(marker) >= fence_len
                and rest.strip() == ""
            ):
                in_fence = False
                fence_char = None
                fence_len = 0
            continue
        if in_fence:
            continue
        yield i, line


def _bullets(body: str) -> list[str]:
    """Extract bullets/numbered items from body text OUTSIDE code fences only."""
    items: list[str] = []
    for _, line in _iter_outside_fences(body.split("\n")):
        s = line.strip()
        if re.match(r"^[-*+]\s+", s):
            items.append(re.sub(r"^[-*+]\s+", "", s))
        elif re.match(r"^\d+\.\s+", s):
            items.append(re.sub(r"^\d+\.\s+", "", s))
    return items


def _split_official_sections(text: str) -> dict[str, str]:
    """
    Split markdown on official Result headings that appear OUTSIDE fenced
    code blocks. Headings inside fences are ignored.

    Fence rules (CommonMark-style): track fence character (backtick vs tilde)
    and opening length; a closer must use the same character with length
    >= opening length. A shorter fence of the same character (e.g. ``` inside
    a ```` fence) does not close the outer fence.

    Duplicate official headings: first occurrence opens the section; a later
    duplicate of the SAME key appends to that section body with _DUP_SECTION_SEP
    (do not restart — callers merge bullets across the concatenated body).
    """
    lines = text.split("\n")
    # Collect (key, body_start_line_index) in document order; body runs until
    # the next official heading (or EOF).
    opens: list[tuple[str, int]] = []  # (key, first line of body)

    for i, line in _iter_outside_fences(lines):
        hm = _HEADING_LINE_RE.match(line)
        if not hm:
            continue
        key = _official_section_key(hm.group(2))
        if key is None:
            continue
        opens.append((key, i + 1))  # body starts on next line

    bodies: dict[str, str] = {}
    for idx, (key, start) in enumerate(opens):
        end = opens[idx + 1][1] - 1 if idx + 1 < len(opens) else len(lines)
        # end is the line index of the next heading; body is start..end-1
        # When next heading is at line H, opens[idx+1][1] == H+1, so end-1 == H
        # Wait: opens stores body_start = heading_line + 1. Next open's body_start
        # is next_heading+1, so body for current is lines[start : next_heading].
        # next_heading = opens[idx+1][1] - 1
        if idx + 1 < len(opens):
            next_heading_line = opens[idx + 1][1] - 1
            chunk = "\n".join(lines[start:next_heading_line])
        else:
            chunk = "\n".join(lines[start:])
        if key in bodies:
            # CB-007: append duplicate occurrence; do not replace.
            bodies[key] = bodies[key] + _DUP_SECTION_SEP + chunk
        else:
            bodies[key] = chunk
    return bodies


def parse_result_markdown(text: str) -> dict:
    """Parse Result Markdown: full section bodies + structured bullet lists."""
    data: dict = {
        "changes": [],
        "verification_evidence": [],
        "blockers": [],
        "next_action": "",
        "new_decisions": [],
        "new_assumptions": [],
        "based_on_version": "",
        "author": "",
        "handoff_id": "",
        "project": "",
        "raw_markdown": text,
        "section_bodies": {},
    }
    # Meta table
    for m in re.finditer(
        r"\|\s*(Project|Task ID|Based on version|Author|Version)\s*\|\s*([^|]+)\|",
        text,
        re.IGNORECASE,
    ):
        field = m.group(1).strip().lower()
        value = m.group(2).strip()
        if field == "project":
            data["project"] = value
        elif field == "task id":
            data["handoff_id"] = value
        elif field == "based on version":
            data["based_on_version"] = value
        elif field == "version" and not data["based_on_version"]:
            data["based_on_version"] = value
        elif field == "author":
            data["author"] = value

    bodies = _split_official_sections(text)
    data["section_bodies"] = dict(bodies)

    # Structured lists — bullets() over full (possibly concatenated) bodies.
    if "changes" in bodies:
        data["changes"] = _bullets(bodies["changes"])
    if "verification_evidence" in bodies:
        data["verification_evidence"] = _bullets(bodies["verification_evidence"])
    if "blockers" in bodies:
        data["blockers"] = _bullets(bodies["blockers"])
    if "decisions" in bodies:
        data["new_decisions"] = _bullets(bodies["decisions"])
    if "assumptions" in bodies:
        data["new_assumptions"] = _bullets(bodies["assumptions"])
    if "next_action" in bodies:
        body = bodies["next_action"]
        b = _bullets(body)
        if b:
            data["next_action"] = "\n".join(b)
        else:
            # Prose next-action: keep non-empty lines outside fences only.
            lines_out: list[str] = []
            for _, line in _iter_outside_fences(body.split("\n")):
                s = line.strip()
                if s:
                    lines_out.append(s)
            data["next_action"] = "\n".join(lines_out)

    return data


def scrub_result_record(result: ResultRecord) -> ResultRecord:
    """Scrub raw_markdown, section_bodies, and structured list strings in place."""
    result.raw_markdown = scrub_text(result.raw_markdown or "")
    result.section_bodies = {
        str(k): scrub_text(str(v)) for k, v in (result.section_bodies or {}).items()
    }
    result.changes = [scrub_text(c) for c in result.changes]
    result.verification_evidence = [
        scrub_text(c) for c in result.verification_evidence
    ]
    result.blockers = [scrub_text(c) for c in result.blockers]
    result.new_decisions = [scrub_text(c) for c in result.new_decisions]
    result.new_assumptions = [scrub_text(c) for c in result.new_assumptions]
    result.next_action = scrub_text(result.next_action or "")
    result.author = scrub_text(result.author or "")
    result.handoff_id = scrub_text(result.handoff_id or "")
    result.project = scrub_text(result.project or "")
    result.based_on_version = scrub_text(result.based_on_version or "")
    return result


def load_result(path: Path) -> ResultRecord:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        raw = json.loads(text)
        # Ensure raw_markdown present for JSON imports when absent
        if "raw_markdown" not in raw and isinstance(raw, dict):
            raw = dict(raw)
            raw.setdefault("raw_markdown", "")
            raw.setdefault("section_bodies", {})
    else:
        raw = parse_result_markdown(text)
    if (
        not raw.get("changes")
        and not raw.get("verification_evidence")
        and not raw.get("next_action")
        and not (raw.get("section_bodies") or {}).get("changes")
    ):
        raise ResultImportError(
            "Result must include changes, verification evidence, blockers, and/or next action."
        )
    result = ResultRecord.from_dict(raw)
    return scrub_result_record(result)


def _parse_version(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v or "0")
    return tuple(int(x) for x in nums) if nums else (0,)


def detect_flags(ctx: ProjectContext, result: ResultRecord) -> list[dict]:
    """Flag outdated or conflicting updates."""
    flags: list[dict] = []
    now = utc_now_iso()

    if result.based_on_version and ctx.current_version:
        if _parse_version(result.based_on_version) < _parse_version(ctx.current_version):
            flags.append(
                {
                    "type": "outdated",
                    "at": now,
                    "message": (
                        f"Result based on version {result.based_on_version} but "
                        f"project is at {ctx.current_version}."
                    ),
                    "author": result.author,
                    "handoff_id": result.handoff_id,
                }
            )
        elif _parse_version(result.based_on_version) > _parse_version(ctx.current_version):
            flags.append(
                {
                    "type": "version_ahead",
                    "at": now,
                    "message": (
                        f"Result claims version {result.based_on_version} ahead of "
                        f"project {ctx.current_version}."
                    ),
                    "author": result.author,
                    "handoff_id": result.handoff_id,
                }
            )

    existing = {d.strip().lower() for d in ctx.decisions}
    for nd in result.new_decisions:
        # Conflict heuristic: "no X" / "not X" opposing an existing decision containing X
        low = nd.strip().lower()
        for ed in ctx.decisions:
            ed_low = ed.strip().lower()
            if low == ed_low:
                continue
            # Explicit negate pattern
            if low.startswith("no ") or low.startswith("not ") or " instead of " in low:
                # Check overlap of significant tokens
                tokens = set(re.findall(r"[a-z0-9]{4,}", low))
                ed_tokens = set(re.findall(r"[a-z0-9]{4,}", ed_low))
                if tokens & ed_tokens:
                    flags.append(
                        {
                            "type": "conflict",
                            "at": now,
                            "message": (
                                f"New decision may conflict with existing: "
                                f"NEW «{nd}» vs EXISTING «{ed}»"
                            ),
                            "author": result.author,
                            "handoff_id": result.handoff_id,
                        }
                    )
                    break
        if low in existing:
            # duplicate — not a conflict
            pass

    if result.handoff_id and ctx.current_task_id and result.handoff_id != ctx.current_task_id:
        flags.append(
            {
                "type": "task_mismatch",
                "at": now,
                "message": (
                    f"Result task ID {result.handoff_id} does not match "
                    f"current {ctx.current_task_id}."
                ),
                "author": result.author,
                "handoff_id": result.handoff_id,
            }
        )

    return flags


def apply_result(ctx: ProjectContext, result: ResultRecord) -> tuple[ProjectContext, list[dict]]:
    """
    Merge result into context. Preserves earlier decisions; appends new ones.
    Returns (updated_ctx, new_flags).
    """
    # CB-007: ensure scrubbed before persist (also done in load_result)
    scrub_result_record(result)

    flags = detect_flags(ctx, result)
    if not result.verification_evidence:
        flags.append(
            {
                "type": "missing_evidence",
                "at": utc_now_iso(),
                "message": "Result has no verification evidence.",
                "author": result.author,
                "handoff_id": result.handoff_id,
            }
        )

    # Snapshot decisions
    ctx.decision_history.append(
        {
            "at": utc_now_iso(),
            "version": ctx.current_version,
            "decisions": list(ctx.decisions),
            "event": "pre_result_snapshot",
            "result_author": result.author,
        }
    )

    existing_d = {d.strip().lower() for d in ctx.decisions}
    for d in result.new_decisions:
        if d.strip().lower() not in existing_d:
            ctx.decisions.append(d)
            existing_d.add(d.strip().lower())

    existing_a = {a.strip().lower() for a in ctx.assumptions}
    for a in result.new_assumptions:
        if a.strip().lower() not in existing_a:
            ctx.assumptions.append(a)
            existing_a.add(a.strip().lower())

    ctx.flags.extend(flags)
    ctx.updated_at = utc_now_iso()

    # Persist result artifact (write_json scrub_obj again)
    d = store.project_dir(ctx.project) / "results"
    d.mkdir(parents=True, exist_ok=True)
    stamp = result.imported_at.replace(":", "").replace("-", "")
    fname = f"{result.handoff_id or 'result'}-{stamp}.json"
    store.write_json(d / fname, result.to_dict())

    return ctx, flags
