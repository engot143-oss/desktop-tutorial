"""Data models for Context Bridge handoffs, context, and results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class GlowPlan:
    """Glow's four-section plan — preserved exactly (raw bodies + structured views)."""

    goal: str = ""
    constraints: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    who_gets_what_next: dict[str, str] = field(default_factory=dict)
    # Exact section bodies (no surrounding strip) for round-trip fidelity (CB-004/005)
    raw_sections: dict[str, str] = field(default_factory=dict)
    # Original line ending preserved for CRLF documents (CB-005)
    line_ending: str = "\n"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GlowPlan:
        raw_who = data.get("who_gets_what_next") or {}
        # N2: ignore nested credentials_included / non-string junk from older exports
        who = {
            str(k): str(v)
            for k, v in dict(raw_who).items()
            if k != "credentials_included" and isinstance(v, (str, int, float))
        }
        raw_sections = {
            str(k): str(v)
            for k, v in dict(data.get("raw_sections") or {}).items()
            if isinstance(v, str)
        }
        le = data.get("line_ending") or "\n"
        if le not in ("\n", "\r\n"):
            le = "\n"
        return cls(
            goal=data.get("goal", "") or "",
            constraints=list(data.get("constraints") or []),
            open_questions=list(data.get("open_questions") or []),
            who_gets_what_next=who,
            raw_sections=raw_sections,
            line_ending=le,
        )


@dataclass
class AssignedTask:
    assignee: str
    tasks: list[str] = field(default_factory=list)
    completion_criteria: str = ""
    blocked_until: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "assignee": self.assignee,
            "tasks": list(self.tasks),
            "completion_criteria": self.completion_criteria,
        }
        if self.blocked_until:
            d["blocked_until"] = self.blocked_until
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssignedTask:
        return cls(
            assignee=data.get("assignee", ""),
            tasks=list(data.get("tasks") or []),
            completion_criteria=data.get("completion_criteria", "") or "",
            blocked_until=data.get("blocked_until"),
        )


@dataclass
class ProjectContext:
    """Persisted project context across handoffs."""

    project: str
    repo_path: str | None = None
    domain: str = "engineering"
    current_task_id: str | None = None
    current_version: str = "1.0.0"
    decisions: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    assigned_tasks: list[AssignedTask] = field(default_factory=list)
    glow_plan: GlowPlan | None = None
    decision_history: list[dict[str, Any]] = field(default_factory=list)
    flags: list[dict[str, Any]] = field(default_factory=list)
    updated_at: str = field(default_factory=utc_now_iso)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "repo_path": self.repo_path,
            "domain": self.domain,
            "current_task_id": self.current_task_id,
            "current_version": self.current_version,
            "decisions": list(self.decisions),
            "assumptions": list(self.assumptions),
            "assigned_tasks": [t.to_dict() for t in self.assigned_tasks],
            "glow_plan": self.glow_plan.to_dict() if self.glow_plan else None,
            "decision_history": list(self.decision_history),
            "flags": list(self.flags),
            "updated_at": self.updated_at,
            "created_at": self.created_at,
            "credentials_included": False,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectContext:
        plan_data = data.get("glow_plan")
        return cls(
            project=data["project"],
            repo_path=data.get("repo_path"),
            domain=data.get("domain", "engineering"),
            current_task_id=data.get("current_task_id"),
            current_version=data.get("current_version", "1.0.0"),
            decisions=list(data.get("decisions") or []),
            assumptions=list(data.get("assumptions") or []),
            assigned_tasks=[
                AssignedTask.from_dict(t) for t in (data.get("assigned_tasks") or [])
            ],
            glow_plan=GlowPlan.from_dict(plan_data) if plan_data else None,
            decision_history=list(data.get("decision_history") or []),
            flags=list(data.get("flags") or []),
            updated_at=data.get("updated_at", utc_now_iso()),
            created_at=data.get("created_at", utc_now_iso()),
        )


@dataclass
class HandoffRecord:
    """Full handoff for a recipient — Markdown + JSON export shape."""

    handoff_id: str
    project: str
    version: str
    recipient: str
    date: str
    source: str
    repo_path: str | None
    glow_plan: GlowPlan
    decisions: list[str]
    assumptions: list[str]
    assigned_tasks: list[AssignedTask]
    next_action: str = ""
    flags: list[dict[str, Any]] = field(default_factory=list)
    credentials_included: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "handoff_id": self.handoff_id,
            "project": self.project,
            "version": self.version,
            "recipient": self.recipient,
            "date": self.date,
            "source": self.source,
            "repo_path": self.repo_path,
            "credentials_included": False,
            "glow_plan": self.glow_plan.to_dict(),
            "decisions": list(self.decisions),
            "assumptions": list(self.assumptions),
            "assigned_tasks": [t.to_dict() for t in self.assigned_tasks],
            "next_action": self.next_action,
            "flags": list(self.flags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HandoffRecord:
        return cls(
            handoff_id=data["handoff_id"],
            project=data["project"],
            version=data.get("version", "1.0.0"),
            recipient=data.get("recipient", ""),
            date=data.get("date", ""),
            source=data.get("source", ""),
            repo_path=data.get("repo_path"),
            glow_plan=GlowPlan.from_dict(data.get("glow_plan") or {}),
            decisions=list(data.get("decisions") or []),
            assumptions=list(data.get("assumptions") or []),
            assigned_tasks=[
                AssignedTask.from_dict(t) for t in (data.get("assigned_tasks") or [])
            ],
            next_action=data.get("next_action", "") or "",
            flags=list(data.get("flags") or []),
            credentials_included=False,
        )


@dataclass
class ResultRecord:
    """Result import: changes, verification, blockers, next action."""

    handoff_id: str
    project: str
    based_on_version: str
    author: str
    changes: list[str] = field(default_factory=list)
    verification_evidence: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    next_action: str = ""
    new_decisions: list[str] = field(default_factory=list)
    new_assumptions: list[str] = field(default_factory=list)
    imported_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResultRecord:
        return cls(
            handoff_id=data.get("handoff_id", ""),
            project=data.get("project", ""),
            based_on_version=data.get("based_on_version", ""),
            author=data.get("author", ""),
            changes=list(data.get("changes") or []),
            verification_evidence=list(data.get("verification_evidence") or []),
            blockers=list(data.get("blockers") or []),
            next_action=data.get("next_action", "") or "",
            new_decisions=list(data.get("new_decisions") or []),
            new_assumptions=list(data.get("new_assumptions") or []),
            imported_at=data.get("imported_at", utc_now_iso()),
        )
