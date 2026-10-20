"""Local filesystem store for project context, handoffs, and results."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .models import ProjectContext, utc_now_iso

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "projects"

# Plans and results are Markdown. 1 MiB is far above any real handoff.
MAX_INPUT_BYTES = 1_048_576


class ProjectNameError(ValueError):
    """Project name is empty, punctuation-only, or collides with another name."""


class InputError(ValueError):
    """A user-supplied file cannot be read as bounded UTF-8 text."""


def _slug(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "project"


def validate_project_name(name: str) -> str:
    """Reject empty and punctuation-only names. Return the stripped name."""
    stripped = (name or "").strip()
    if not any(ch.isalnum() for ch in stripped):
        raise ProjectNameError("Project name must include a letter or digit.")
    return stripped


def require_path_segment(value: str, label: str) -> str:
    """Reject values that are not a single safe filename segment."""
    text = "" if value is None else str(value).strip()
    unsafe = (
        not text
        or text in {".", ".."}
        or any(ch in text for ch in "/\\\x00\n\r")
        or any(part in {".", ".."} for part in Path(text).parts)
    )
    if unsafe:
        raise ValueError(
            f"{label} {value!r} is not a safe file name "
            "(empty names, path separators, and '..' are not allowed)"
        )
    return text


def path_inside(root: Path, name: str) -> Path:
    """Resolve ``root/name`` and refuse anything that escapes ``root``."""
    root_resolved = root.resolve()
    relative = Path(name)
    if (
        not name
        or relative.is_absolute()
        or any(ch in name for ch in "/\\\x00")
        or any(part in {".", ".."} for part in relative.parts)
    ):
        raise ValueError(f"refusing to write outside {root_resolved}: {name!r}")
    candidate = (root_resolved / relative).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        raise ValueError(
            f"refusing to write outside {root_resolved}: {name!r}"
        ) from None
    return candidate


def filename_stamp() -> str:
    """UTC stamp with microseconds, safe in Windows filenames (no ':')."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def unique_stem(
    directory: Path,
    prefix: str,
    suffixes: tuple[str, ...] = (".md", ".json"),
) -> str:
    """Return ``prefix-stamp`` that does not already exist for any suffix.

    A second write in the same microsecond gets ``-2``, ``-3``, and so on
    instead of overwriting the first file.
    """
    if any(ch in prefix for ch in "/\\\x00") or any(
        part in {".", ".."} for part in Path(prefix).parts
    ):
        raise ValueError(f"refusing to write outside {directory}: {prefix!r}")
    stamp = filename_stamp()
    stem = f"{prefix}-{stamp}"
    n = 2
    while any((directory / f"{stem}{suffix}").exists() for suffix in suffixes):
        stem = f"{prefix}-{stamp}-{n}"
        n += 1
        if n > 1000:
            raise ValueError("could not choose a free file name")
    return stem


def read_text_file(path: Path) -> str:
    """Read a regular file as UTF-8, rejecting directories, binary, and oversize input."""
    path = Path(path)
    if path.is_dir():
        raise InputError(f"path is a directory: {path}")
    if not path.is_file():
        raise InputError(f"file not found: {path}")
    size = path.stat().st_size
    if size > MAX_INPUT_BYTES:
        raise InputError(f"file exceeds the 1 MiB limit ({size} bytes): {path}")
    try:
        data = path.read_bytes()
    except IsADirectoryError:
        raise InputError(f"path is a directory: {path}") from None
    except OSError as exc:
        raise InputError(f"could not read {path}: {exc.strerror or exc}") from None
    if len(data) > MAX_INPUT_BYTES:
        raise InputError(
            f"file exceeds the 1 MiB limit ({len(data)} bytes): {path}"
        )
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise InputError(f"file is not valid UTF-8: {path}") from None


def project_dir(project: str) -> Path:
    return DATA_DIR / _slug(project)


def _read_context(path: Path) -> ProjectContext:
    data = json.loads(path.read_text(encoding="utf-8"))
    return ProjectContext.from_dict(data)


def _reject_slug_collision(requested: str, ctx: ProjectContext) -> None:
    stored = (ctx.project or "").strip()
    if stored != requested:
        raise ProjectNameError(
            f"Project name '{requested}' uses the same folder as existing project "
            f"'{ctx.project}' ({_slug(requested)}). Refusing to share that folder."
        )


def ensure_project(project: str, repo_path: str | None = None) -> ProjectContext:
    name = validate_project_name(project)
    d = project_dir(name)
    ctx_path = d / "context.json"
    if ctx_path.is_file():
        ctx = _read_context(ctx_path)
        _reject_slug_collision(name, ctx)
        return ctx
    d.mkdir(parents=True, exist_ok=True)
    (d / "handoffs").mkdir(exist_ok=True)
    (d / "results").mkdir(exist_ok=True)
    (d / "exports").mkdir(exist_ok=True)
    ctx = ProjectContext(project=name, repo_path=repo_path)
    save_context(ctx)
    return ctx


def load_context(project: str) -> ProjectContext:
    name = validate_project_name(project)
    path = project_dir(name) / "context.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"No project context for '{project}'. Run: cb init \"{project}\""
        )
    ctx = _read_context(path)
    _reject_slug_collision(name, ctx)
    return ctx


def iter_project_contexts() -> list[ProjectContext]:
    """Load every saved project by its folder, for ``cb status`` listing."""
    if not DATA_DIR.exists():
        return []
    found: list[ProjectContext] = []
    for path in sorted(DATA_DIR.iterdir()):
        ctx_path = path / "context.json"
        if ctx_path.is_file():
            found.append(_read_context(ctx_path))
    return found


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
