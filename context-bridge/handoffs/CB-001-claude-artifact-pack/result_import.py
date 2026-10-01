"""Import results and flag conflicting / outdated updates."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .models import ProjectContext, ResultRecord, utc_now_iso
from . import store


class ResultImportError(ValueError):
    pass


def parse_result_markdown(text: str) -> dict:
    """Parse a simple result Markdown with known headings."""
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

    heading_re = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.MULTILINE)
    parts = heading_re.split(text)
    i = 1

    def bullets(body: str) -> list[str]:
        items = []
        for line in body.split("\n"):
            s = line.strip()
            if re.match(r"^[-*+]\s+", s):
                items.append(re.sub(r"^[-*+]\s+", "", s))
            elif re.match(r"^\d+\.\s+", s):
                items.append(re.sub(r"^\d+\.\s+", "", s))
        return items

    while i + 2 < len(parts):
        title = parts[i + 1].strip().lower()
        body = parts[i + 2]
        if title.startswith("change"):
            data["changes"] = bullets(body)
        elif title.startswith("verification"):
            data["verification_evidence"] = bullets(body)
        elif title.startswith("blocker"):
            data["blockers"] = bullets(body)
        elif title.startswith("next action"):
            data["next_action"] = body.strip()
            # or first bullet
            b = bullets(body)
            if b and not data["next_action"]:
                data["next_action"] = b[0]
            elif b and len(data["next_action"].split("\n")[0]) < 3:
                data["next_action"] = b[0]
            else:
                # prefer non-empty paragraph
                para = body.strip()
                if para:
                    data["next_action"] = para.split("\n")[0].strip()
        elif title.startswith("new decision") or title == "decisions added":
            data["new_decisions"] = bullets(body)
        elif title.startswith("new assumption"):
            data["new_assumptions"] = bullets(body)
        i += 3
    return data


def load_result(path: Path) -> ResultRecord:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        raw = json.loads(text)
    else:
        raw = parse_result_markdown(text)
    if not raw.get("changes") and not raw.get("verification_evidence") and not raw.get("next_action"):
        raise ResultImportError(
            "Result must include changes, verification evidence, blockers, and/or next action."
        )
    return ResultRecord.from_dict(raw)


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
    flags = detect_flags(ctx, result)

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

    # Persist result artifact
    d = store.project_dir(ctx.project) / "results"
    d.mkdir(parents=True, exist_ok=True)
    stamp = result.imported_at.replace(":", "").replace("-", "")
    fname = f"{result.handoff_id or 'result'}-{stamp}.json"
    store.write_json(d / fname, result.to_dict())

    return ctx, flags
