"""Local filesystem store for project context, handoffs, and results."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .models import ProjectContext, utc_now_iso

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "projects"


def _slug(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "project"


def project_dir(project: str) -> Path:
    return DATA_DIR / _slug(project)


def ensure_project(project: str, repo_path: str | None = None) -> ProjectContext:
    d = project_dir(project)
    d.mkdir(parents=True, exist_ok=True)
    (d / "handoffs").mkdir(exist_ok=True)
    (d / "results").mkdir(exist_ok=True)
    (d / "exports").mkdir(exist_ok=True)
    ctx_path = d / "context.json"
    if ctx_path.exists():
        return load_context(project)
    ctx = ProjectContext(project=project, repo_path=repo_path)
    save_context(ctx)
    return ctx


def load_context(project: str) -> ProjectContext:
    path = project_dir(project) / "context.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No project context for '{project}'. Run: cb init \"{project}\""
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return ProjectContext.from_dict(data)


def save_context(ctx: ProjectContext) -> Path:
    d = project_dir(ctx.project)
    d.mkdir(parents=True, exist_ok=True)
    (d / "handoffs").mkdir(exist_ok=True)
    (d / "results").mkdir(exist_ok=True)
    (d / "exports").mkdir(exist_ok=True)
    ctx.updated_at = utc_now_iso()
    path = d / "context.json"
    from .scrub import scrub_obj

    # CB-004: scrub secrets in persisted context (metadata, blocked_until, bodies)
    sanitized = scrub_obj(ctx.to_dict(), root=True)
    path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
    return path


def write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Scrub credential-like keys AND free-text patterns (v1.1)
    from .scrub import scrub_obj

    sanitized = scrub_obj(data, root=True)
    path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
    return path


def list_projects() -> list[str]:
    if not DATA_DIR.exists():
        return []
    return sorted(p.name for p in DATA_DIR.iterdir() if (p / "context.json").exists())
