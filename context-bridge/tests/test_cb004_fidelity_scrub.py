"""CB-004 regressions: exact four-section contract + scrub on all export surfaces."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from context_bridge import store
from context_bridge.export import export_handoff, render_markdown
from context_bridge.models import AssignedTask, GlowPlan, HandoffRecord, ProjectContext
from context_bridge.plan_import import PlanImportError, parse_glow_plan_markdown
from context_bridge.scrub import scrub_text

SECRET = "sk-SYNTHETICSECRETKEY99xyz"
SECRET2 = "token=leak-me-please-now"


def _plan_md(
    *,
    order=None,
    goal_body=None,
    titles=None,
    duplicate_goal=False,
    extra_meta_secret=False,
    blocked_secret=False,
) -> str:
    titles = titles or {
        "goal": "Goal",
        "constraints": "Constraints",
        "open_questions": "Open questions",
        "who_gets_what_next": "Who gets what next",
    }
    order = order or [
        "goal",
        "constraints",
        "open_questions",
        "who_gets_what_next",
    ]
    # Intentional leading/trailing whitespace inside Goal for fidelity check
    if goal_body is None:
        goal_body = f"\n  Ship the widget with {SECRET} in prose.\n  Second line kept.\n"

    bodies = {
        "goal": goal_body,
        "constraints": "\n- Local only.\n- No deploy.\n",
        "open_questions": "\n- None blocking.\n",
        "who_gets_what_next": "\n- **Claude:** Implement.\n- **Grok:** Second opinion.\n",
    }

    project = f"Secret Project {SECRET2}" if extra_meta_secret else "Fidelity Demo"
    source = f"Glow ({SECRET})" if extra_meta_secret else "Glow"

    parts = [
        f"# Handoff FID-001 — {project}",
        "",
        "| Field | Value |",
        "|-------|--------|",
        f"| Project | {project} |",
        "| Task ID | FID-001 |",
        "| Version | 1.1.1 |",
        f"| Source | {source} |",
        "| Repo / path | /workspace/context-bridge |",
        "",
        "## Glow plan (preserved)",
        "",
    ]
    for key in order:
        parts.append(f"### {titles[key]}")
        parts.append(bodies[key].rstrip("\n"))
        parts.append("")
        if duplicate_goal and key == "goal":
            parts.append("### Goal")
            parts.append("Duplicate body")
            parts.append("")

    parts.extend(
        [
            "## Decisions",
            "- Keep fidelity.",
            "",
            "## Assigned tasks",
            "",
            "### Claude — coding",
            "1. Do the work.",
            "",
            "**Completion criteria:** Done.",
        ]
    )
    if blocked_secret:
        parts.append(f"**Blocked until:** waiting on {SECRET}")
    parts.append("")
    return "\n".join(parts)


class ExactFourSectionTests(unittest.TestCase):
    def test_accepts_exact_order_and_preserves_goal_whitespace(self):
        md = _plan_md()
        plan, meta, *_ = parse_glow_plan_markdown(md)
        raw_goal = plan.raw_sections["goal"]
        # Surrounding whitespace / internal lines not collapsed
        self.assertTrue(raw_goal.startswith("\n") or "  Ship" in raw_goal)
        self.assertIn("  Ship the widget", raw_goal)
        self.assertIn("  Second line kept.", raw_goal)
        # Must NOT be joined into a single spaced line losing indent
        self.assertNotIn("prose. Second line", raw_goal.replace("\n", " "))
        self.assertIn("Second line kept.", raw_goal)

    def test_rejects_reordered_sections(self):
        md = _plan_md(
            order=["constraints", "goal", "open_questions", "who_gets_what_next"]
        )
        with self.assertRaises(PlanImportError) as cm:
            parse_glow_plan_markdown(md)
        self.assertIn("order", str(cm.exception).lower())

    def test_rejects_altered_heading(self):
        md = _plan_md(titles={
            "goal": "Goals",  # altered
            "constraints": "Constraints",
            "open_questions": "Open questions",
            "who_gets_what_next": "Who gets what next",
        })
        with self.assertRaises(PlanImportError):
            parse_glow_plan_markdown(md)

    def test_rejects_open_question_singular(self):
        md = _plan_md(titles={
            "goal": "Goal",
            "constraints": "Constraints",
            "open_questions": "Open question",
            "who_gets_what_next": "Who gets what next",
        })
        with self.assertRaises(PlanImportError):
            parse_glow_plan_markdown(md)

    def test_rejects_duplicate_goal(self):
        md = _plan_md(duplicate_goal=True)
        with self.assertRaises(PlanImportError) as cm:
            parse_glow_plan_markdown(md)
        self.assertIn("Duplicate", str(cm.exception))

    def test_round_trip_body_fidelity(self):
        """Export then re-import preserves Goal body whitespace (minus scrubbed secrets)."""
        tmp = Path(tempfile.mkdtemp(prefix="cb-fid-"))
        orig = store.DATA_DIR
        try:
            store.DATA_DIR = tmp / "projects"
            md = _plan_md(goal_body="\n  Keep indent.\n\n  Blank line above.\n")
            # Use a goal without secrets so scrub doesn't alter fidelity check
            md = md.replace(SECRET, "NOSCRET")
            plan, *_ = parse_glow_plan_markdown(md)
            ctx = store.ensure_project("Fidelity Demo")
            ctx.current_task_id = "FID-001"
            ctx.current_version = "1.1.1"
            ctx.glow_plan = plan
            ctx.decisions = ["Keep fidelity."]
            store.save_context(ctx)
            md_path, _, _ = export_handoff(ctx, "Claude", out_dir=tmp / "out")
            exported = md_path.read_text(encoding="utf-8")
            plan2, *_ = parse_glow_plan_markdown(exported)
            self.assertEqual(
                plan2.raw_sections["goal"],
                plan.raw_sections["goal"],
            )
            self.assertIn("  Keep indent.", plan2.raw_sections["goal"])
            self.assertIn("\n\n  Blank line above.", plan2.raw_sections["goal"])
        finally:
            store.DATA_DIR = orig
            shutil.rmtree(tmp, ignore_errors=True)


class ScrubAllSurfacesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cb-scrub4-"))
        self._orig = store.DATA_DIR
        store.DATA_DIR = self.tmp / "projects"

    def tearDown(self):
        store.DATA_DIR = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_secret_scrubbed_from_metadata_and_blocked_until_md_and_json(self):
        md = _plan_md(extra_meta_secret=True, blocked_secret=True)
        plan, meta, _d, _a, assigned = parse_glow_plan_markdown(md)
        self.assertTrue(assigned)
        self.assertIn(SECRET, assigned[0].blocked_until or "")

        ctx = store.ensure_project(meta["project"] or "Secret Project")
        ctx.project = meta["project"] or ctx.project
        ctx.current_task_id = "FID-001"
        ctx.current_version = "1.1.1"
        ctx.repo_path = "/workspace/context-bridge"
        ctx.glow_plan = plan
        ctx.assigned_tasks = assigned
        ctx.decisions = ["local-only"]
        # Source-like secret also planted via decisions for belt-and-suspenders
        store.save_context(ctx)

        md_path, json_path, _h = export_handoff(
            ctx, "Claude", out_dir=self.tmp / "out", source=f"Glow ({SECRET})"
        )
        md_text = md_path.read_text(encoding="utf-8")
        json_text = json_path.read_text(encoding="utf-8")
        data = json.loads(json_text)

        # Must not leak synthetic key on any surface
        for label, text in [("md", md_text), ("json", json_text)]:
            self.assertNotIn(SECRET, text, f"leaked in {label}")
            self.assertNotIn("leak-me-please-now", text, f"token leaked in {label}")

        # Blocked until line present but redacted
        self.assertIn("Blocked until", md_text)
        self.assertIn("[REDACTED", md_text)

        # Project metadata table scrubbed
        self.assertNotIn(SECRET2.split("=", 1)[1], md_text)

        # JSON blocked_until scrubbed
        tasks = data.get("assigned_tasks") or []
        self.assertTrue(tasks)
        bu = tasks[0].get("blocked_until") or ""
        self.assertNotIn(SECRET, bu)
        self.assertIn("REDACTED", bu.upper())

        # Goal scrubbed in JSON too
        goal = (data.get("glow_plan") or {}).get("goal") or ""
        self.assertNotIn(SECRET, goal)

    def test_scrub_text_direct(self):
        self.assertNotIn(SECRET, scrub_text(f"see {SECRET} here"))
        self.assertNotIn("leak-me", scrub_text(SECRET2))


if __name__ == "__main__":
    unittest.main()
