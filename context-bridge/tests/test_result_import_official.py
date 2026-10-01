"""Regression: official Result template (## Decisions + multi-bullet Next action)."""

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
from context_bridge.models import ProjectContext, GlowPlan
from context_bridge.result_import import apply_result, load_result, parse_result_markdown
from context_bridge.cli import main as cli_main

OFFICIAL = ROOT / "handoffs" / "CB-001-claude-result-v2.md"


class OfficialResultImportTests(unittest.TestCase):
    def test_parse_decisions_and_full_next_action(self):
        data = parse_result_markdown(OFFICIAL.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["new_decisions"]), 4)
        self.assertTrue(
            any("conditional pass" in d for d in data["new_decisions"]),
            data["new_decisions"],
        )
        self.assertTrue(
            any("import contract" in d for d in data["new_decisions"]),
            data["new_decisions"],
        )
        na = data["next_action"]
        self.assertIn("Grok Bot:", na)
        self.assertIn("Enrique:", na)
        self.assertIn("Glow:", na)
        self.assertNotRegex(na, r"(?m)^-\s")
        # all three bullets preserved (joined by newlines)
        self.assertEqual(na.count("\n"), 2)

    def test_cli_fallbacks_set_task_id_and_version(self):
        """B1: --task-id / --based-on-version enable checks without a meta table."""
        tmp = Path(tempfile.mkdtemp(prefix="cb-reg-"))
        try:
            # Point store at a temp data dir
            original = store.DATA_DIR
            store.DATA_DIR = tmp / "projects"
            store.DATA_DIR.mkdir(parents=True)

            ctx = store.ensure_project("Regression Project")
            ctx.current_task_id = "CB-001"
            ctx.current_version = "1.0.1"
            ctx.decisions = ["v1 is local-only."]
            ctx.glow_plan = GlowPlan(
                goal="test",
                constraints=["local"],
                open_questions=[],
                who_gets_what_next={"Claude": "review"},
            )
            store.save_context(ctx)

            # Import via CLI with fallbacks (official Result has no meta table)
            rc = cli_main(
                [
                    "import-result",
                    "Regression Project",
                    str(OFFICIAL),
                    "--author",
                    "Claude",
                    "--task-id",
                    "CB-001",
                    "--based-on-version",
                    "1.0.0",
                ]
            )
            self.assertEqual(rc, 0)

            updated = store.load_context("Regression Project")
            # New decisions from ## Decisions merged
            self.assertTrue(
                any("conditional pass" in d for d in updated.decisions),
                updated.decisions,
            )
            # Earlier decision preserved
            self.assertIn("v1 is local-only.", updated.decisions)
            # Outdated flag should fire: based_on 1.0.0 < project 1.0.1
            types = {f["type"] for f in updated.flags}
            self.assertIn("outdated", types, updated.flags)

            # Result artifact should record task id + full next_action
            results = list((store.project_dir("Regression Project") / "results").glob("*.json"))
            self.assertTrue(results)
            raw = json.loads(results[-1].read_text(encoding="utf-8"))
            self.assertEqual(raw["handoff_id"], "CB-001")
            self.assertEqual(raw["based_on_version"], "1.0.0")
            self.assertIn("Grok Bot:", raw["next_action"])
            self.assertIn("Enrique:", raw["next_action"])
            self.assertIn("Glow:", raw["next_action"])
            self.assertGreaterEqual(len(raw["new_decisions"]), 4)
        finally:
            store.DATA_DIR = original
            shutil.rmtree(tmp, ignore_errors=True)

    def test_load_result_direct(self):
        result = load_result(OFFICIAL)
        self.assertGreaterEqual(len(result.new_decisions), 4)
        self.assertIn("Grok Bot:", result.next_action)
        self.assertIn("\n", result.next_action)


class N1N2SmokeTests(unittest.TestCase):
    def test_completion_criteria_not_in_task_list(self):
        from context_bridge.plan_import import parse_glow_plan_markdown

        md = (ROOT / "handoffs" / "CB-001-glow-plan.md").read_text(encoding="utf-8")
        _plan, _meta, _d, _a, assigned = parse_glow_plan_markdown(md)
        grok = next(t for t in assigned if "Grok" in t.assignee)
        for t in grok.tasks:
            self.assertNotIn("Completion criteria", t, t)
            self.assertNotIn("completion criteria", t.lower(), t)
        self.assertTrue(grok.completion_criteria)
        self.assertNotIn("**Completion criteria:**", grok.completion_criteria)

    def test_credentials_included_not_in_who(self):
        from context_bridge.export import export_handoff
        from context_bridge.models import AssignedTask

        tmp = Path(tempfile.mkdtemp(prefix="cb-n2-"))
        try:
            original = store.DATA_DIR
            store.DATA_DIR = tmp / "projects"
            ctx = store.ensure_project("N2 Project")
            ctx.current_task_id = "N2-1"
            ctx.current_version = "1.0.2"
            ctx.glow_plan = GlowPlan(
                goal="g",
                constraints=["c"],
                open_questions=[],
                who_gets_what_next={"Claude": "review", "Grok Bot": "fix"},
            )
            ctx.decisions = ["v1 is local-only."]
            ctx.flags = [
                {
                    "type": "outdated",
                    "message": "demo flag",
                    "at": "2026-10-01T00:00:00Z",
                }
            ]
            ctx.assigned_tasks = [
                AssignedTask(
                    assignee="Claude",
                    tasks=["Review"],
                    completion_criteria="Written review",
                )
            ]
            store.save_context(ctx)
            md_path, json_path, h = export_handoff(ctx, "Claude", out_dir=tmp / "out")
            data = json.loads(json_path.read_text(encoding="utf-8"))
            who = data["glow_plan"]["who_gets_what_next"]
            self.assertNotIn("credentials_included", who)
            self.assertEqual(data.get("credentials_included"), False)
            self.assertTrue(data.get("flags"))
            md = md_path.read_text(encoding="utf-8")
            self.assertIn("## Open flags", md)
            self.assertIn("[outdated]", md)
            # N1: criteria once, not glued into numbered task
            self.assertIn("**Completion criteria:** Written review", md)
            self.assertNotIn("1. Review **Completion criteria:**", md)
        finally:
            store.DATA_DIR = original
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
