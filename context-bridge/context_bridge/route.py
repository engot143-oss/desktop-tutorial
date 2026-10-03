"""Slice A — route Who gets what next → worker claude | grok."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .models import ProjectContext

WORKERS = ("claude", "grok")

# Names that are hierarchy roles, not coding/explore workers
_ORCHESTRATOR_NAMES = re.compile(
    r"^(grok\s*bot|glow|eric|enrique|context\s*bridge|me\b.*)",
    re.IGNORECASE,
)

_CODING_HINTS = re.compile(
    r"\b(cod(e|ing)|implement|fix|build|patch|adapter|cli|writ(e|ing)|develop|"
    r"refactor|ship|program)\b",
    re.IGNORECASE,
)
_EXPLORE_HINTS = re.compile(
    r"\b(explor(e|ation)|second\s*opinion|research|investigat|survey|compare|"
    r"brainstorm|analyze|analysis)\b",
    re.IGNORECASE,
)


@dataclass
class RouteDecision:
    status: str  # "ok" | "clarify"
    worker: str | None  # "claude" | "grok" | None
    reason: str
    candidates: dict[str, str]
    override_applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_worker_name(name: str) -> str | None:
    n = name.strip().lower()
    n = re.sub(r"\s+", " ", n)
    if _ORCHESTRATOR_NAMES.match(n):
        return None
    if n == "claude" or n.startswith("claude"):
        return "claude"
    # Plain Grok (not Grok Bot) — explore / second opinion
    if n == "grok" or (n.startswith("grok") and "bot" not in n):
        return "grok"
    return None


def extract_worker_assignments(who: dict[str, str]) -> dict[str, str]:
    """Map worker → assignment text from Who gets what next."""
    out: dict[str, str] = {}
    for name, action in (who or {}).items():
        worker = _normalize_worker_name(str(name))
        if worker:
            # Prefer first explicit assignment; concatenate if duplicate keys unlikely
            out[worker] = str(action)
    return out


def _classify_role(text: str) -> str | None:
    coding = bool(_CODING_HINTS.search(text or ""))
    explore = bool(_EXPLORE_HINTS.search(text or ""))
    if coding and not explore:
        return "coding"
    if explore and not coding:
        return "explore"
    if coding and explore:
        return "mixed"
    return None


def route_task(
    ctx: ProjectContext,
    *,
    override: str | None = None,
    role: str | None = None,
    task_id: str | None = None,
) -> RouteDecision:
    """
    Choose claude | grok from Who gets what next.
    Glow override (--override) always wins.
    Ambiguous cases return status=clarify (no worker).
    """
    who = (ctx.glow_plan.who_gets_what_next if ctx.glow_plan else {}) or {}
    candidates = extract_worker_assignments(who)
    tid = task_id or ctx.current_task_id or ""

    if override:
        w = override.strip().lower()
        if w not in WORKERS:
            return RouteDecision(
                status="clarify",
                worker=None,
                reason=f"Invalid override '{override}'. Use claude or grok.",
                candidates=candidates,
                override_applied=False,
            )
        return RouteDecision(
            status="ok",
            worker=w,
            reason=f"Glow override -> {w}"
            + (f" (task {tid})" if tid else ""),
            candidates=candidates,
            override_applied=True,
        )

    if not candidates:
        return RouteDecision(
            status="clarify",
            worker=None,
            reason=(
                "No Claude or Grok assignment in Who gets what next. "
                "Clarify which worker should run"
                + (f" task {tid}." if tid else ".")
            ),
            candidates=candidates,
        )

    if len(candidates) == 1:
        worker, action = next(iter(candidates.items()))
        return RouteDecision(
            status="ok",
            worker=worker,
            reason=f"Sole worker in Who gets what next: {worker} - {action[:120]}",
            candidates=candidates,
        )

    # Both present — use role hint or classify assignment text
    role_l = (role or "").strip().lower() or None
    classified = {w: _classify_role(t) for w, t in candidates.items()}

    if role_l in ("coding", "code"):
        if "claude" in candidates:
            return RouteDecision(
                status="ok",
                worker="claude",
                reason="Role=coding default -> Claude (Glow may override)",
                candidates=candidates,
            )
        return RouteDecision(
            status="clarify",
            worker=None,
            reason="Role=coding but Claude not assigned in Who gets what next.",
            candidates=candidates,
        )

    if role_l in ("explore", "exploration", "second-opinion", "second_opinion"):
        if "grok" in candidates:
            return RouteDecision(
                status="ok",
                worker="grok",
                reason="Role=explore / second-opinion default -> Grok (Glow may override)",
                candidates=candidates,
            )
        return RouteDecision(
            status="clarify",
            worker=None,
            reason="Role=explore but Grok not assigned in Who gets what next.",
            candidates=candidates,
        )

    # No role: if classifications cleanly separate coding vs explore, pick by intent
    if classified.get("claude") == "coding" and classified.get("grok") in (
        "explore",
        None,
    ):
        # Still ambiguous *which* to run now without a role — ask
        return RouteDecision(
            status="clarify",
            worker=None,
            reason=(
                "Both Claude and Grok are assigned. "
                "Pass --role coding|explore or --override claude|grok "
                "(Glow override wins)."
            ),
            candidates=candidates,
        )

    if classified.get("grok") == "explore" and classified.get("claude") in (
        "coding",
        None,
    ):
        return RouteDecision(
            status="clarify",
            worker=None,
            reason=(
                "Both Claude and Grok are assigned. "
                "Pass --role coding|explore or --override claude|grok "
                "(Glow override wins)."
            ),
            candidates=candidates,
        )

    return RouteDecision(
        status="clarify",
        worker=None,
        reason=(
            "Ambiguous route: multiple workers in Who gets what next "
            f"({', '.join(sorted(candidates))}). "
            "Clarify with --override (Glow) or --role."
        ),
        candidates=candidates,
    )
