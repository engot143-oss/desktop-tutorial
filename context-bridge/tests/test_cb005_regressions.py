"""CB-005 regressions: multi-cycle fidelity, CRLF, nested headings, scrub keys, exact titles."""

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
from context_bridge.adapters.manual import create_manual_packet
from context_bridge.export import export_handoff, render_markdown
from context_bridge.glow_pack import write_glow_return_pack
from context_bridge.models import AssignedTask, GlowPlan, ResultRecord
from context_bridge.plan_import import PlanImportError, parse_glow_plan_markdown
from context_bridge.scrub import scrub_obj, scrub_text

SECRET = "sk-SYNTHETICSECRETKEY99xyz"
SECRET_TOKEN = "token=leak-me-please-now"


def _fid_plan(
    *,
    goal=None,
    constraints=None,
    open_questions=None,
    who=None,
    crlf=False,
    nested_in_goal=False,
    title_goal="Goal",
) -> str:
    """Build a plan whose interstitial bodies match EXPECTED_BODIES (LF)."""
    if goal is None:
        goal = EXPECTED_BODIES["goal"]
    if constraints is None:
        constraints = EXPECTED_BODIES["constraints"]
    if open_questions is None:
        open_questions = EXPECTED_BODIES["open_questions"]
    if who is None:
        who = EXPECTED_BODIES["who_gets_what_next"]
    if nested_in_goal:
        goal = (
            "Intro paragraph.\n\n"
            "#### Decisions\n"
            "- nested must stay in Goal\n\n"
            "Still part of Goal."
        )
    # Join as heading + body + heading … Bodies are exact interstitials.
    md = (
        "# Fidelity\n\n"
        "| Field | Value |\n"
        "|-------|--------|\n"
        "| Project | Fid Project |\n"
        "| Task ID | FID-005 |\n"
        "| Version | 1.1.2 |\n"
        "| Source | Glow |\n\n"
        f"### {title_goal}\n"
        f"{goal}\n"
        "### Constraints\n"
        f"{constraints}\n"
        "### Open questions\n"
        f"{open_questions}\n"
        "### Who gets what next\n"
        f"{who}\n"
        "## Decisions\n"
        "- Keep fidelity.\n"
    )
    if crlf:
        md = md.replace("\n", "\r\n")
    return md


# Independently specified expected bodies (LF). Trailing newline means a blank
# line existed before the next heading in the source document.
EXPECTED_BODIES = {
    "goal": "Line one.\n\n  indented\ncontinuation kept.",
    "constraints": "- Local only.\n- Preserve bodies.",
    "open_questions": "- None blocking.",
    "who_gets_what_next": "- **Claude:** Implement.\n- **Grok:** Explore.",
}


class MultiCycleFidelityTests(unittest.TestCase):
    def test_all_four_bodies_stable_across_three_cycles(self):
        """Compare to independently specified expected bodies — not parser echo alone."""
        expected = dict(EXPECTED_BODIES)
        tmp = Path(tempfile.mkdtemp(prefix="cb5-cycle-"))
        orig = store.DATA_DIR
        try:
            store.DATA_DIR = tmp / "projects"
            text = _fid_plan()
            for cycle in range(3):
                plan, *_ = parse_glow_plan_markdown(text)
                for key, exp in expected.items():
                    self.assertEqual(
                        plan.raw_sections[key],
                        exp,
                        f"cycle {cycle} section {key}",
                    )
                ctx = store.ensure_project("Fid Project")
                ctx.current_task_id = "FID-005"
                ctx.current_version = "1.1.2"
                ctx.glow_plan = plan
                ctx.decisions = ["Keep fidelity."]
                store.save_context(ctx)
                md_path, _, _ = export_handoff(ctx, "Claude", out_dir=tmp / "out")
                text = md_path.read_text(encoding="utf-8")
            # final re-import still matches expected
            plan, *_ = parse_glow_plan_markdown(text)
            for key, exp in expected.items():
                self.assertEqual(plan.raw_sections[key], exp, f"final {key}")
        finally:
            store.DATA_DIR = orig
            shutil.rmtree(tmp, ignore_errors=True)


class BodyFidelityTests(unittest.TestCase):
    def test_crlf_preserved_via_file_path(self):
        tmp = Path(tempfile.mkdtemp(prefix="cb5-crlf-"))
        orig = store.DATA_DIR
        try:
            store.DATA_DIR = tmp / "projects"
            src = tmp / "plan.md"
            raw = _fid_plan(crlf=True).encode("utf-8")
            self.assertIn(b"\r\n", raw)
            src.write_bytes(raw)
            # real file import path
            from context_bridge.plan_import import import_plan_file

            ctx = store.ensure_project("Fid Project")
            ctx = import_plan_file(src, ctx, task_id="FID-005", version="1.1.2")
            self.assertEqual(ctx.glow_plan.line_ending, "\r\n")
            self.assertIn("\r\n", ctx.glow_plan.raw_sections["goal"])
            store.save_context(ctx)
            md_path, _, _ = export_handoff(ctx, "Claude", out_dir=tmp / "out")
            out_bytes = md_path.read_bytes()
            self.assertIn(b"\r\n", out_bytes)
            plan2, *_ = parse_glow_plan_markdown(out_bytes.decode("utf-8"))
            self.assertEqual(
                plan2.raw_sections["goal"], ctx.glow_plan.raw_sections["goal"]
            )
            self.assertEqual(plan2.line_ending, "\r\n")
        finally:
            store.DATA_DIR = orig
            shutil.rmtree(tmp, ignore_errors=True)

    def test_nested_decisions_heading_does_not_truncate_goal(self):
        md = _fid_plan(nested_in_goal=True)
        plan, *_ = parse_glow_plan_markdown(md)
        goal = plan.raw_sections["goal"]
        self.assertIn("#### Decisions", goal)
        self.assertIn("nested must stay in Goal", goal)
        self.assertIn("Still part of Goal.", goal)
        # Companion ## Decisions still extracted separately
        _, _, decisions, _, _ = parse_glow_plan_markdown(md)
        self.assertTrue(any("fidelity" in d.lower() for d in decisions))


class ExactTitleTests(unittest.TestCase):
    def test_rejects_lowercase_goal(self):
        with self.assertRaises(PlanImportError):
            parse_glow_plan_markdown(_fid_plan(title_goal="goal"))

    def test_rejects_bold_goal(self):
        with self.assertRaises(PlanImportError):
            parse_glow_plan_markdown(_fid_plan(title_goal="**Goal**"))

    def test_rejects_altered_and_reorder_and_dupes(self):
        with self.assertRaises(PlanImportError):
            parse_glow_plan_markdown(_fid_plan(title_goal="Goals"))
        # reorder
        md = _fid_plan()
        md = md.replace("### Goal\n", "### TMP\n").replace(
            "### Constraints\n", "### Goal\n"
        ).replace("### TMP\n", "### Constraints\n")
        with self.assertRaises(PlanImportError):
            parse_glow_plan_markdown(md)


class ScrubLeakTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cb5-scrub-"))
        self._orig = store.DATA_DIR
        store.DATA_DIR = self.tmp / "projects"

    def tearDown(self):
        store.DATA_DIR = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx_with_secrets(self):
        md = _fid_plan(goal=f"Goal with {SECRET}\n")
        plan, *_ = parse_glow_plan_markdown(md)
        ctx = store.ensure_project(f"Proj {SECRET_TOKEN}")
        ctx.project = f"Proj {SECRET_TOKEN}"
        ctx.current_task_id = f"TID-{SECRET}"
        ctx.current_version = f"1.1.2-{SECRET_TOKEN}"
        ctx.glow_plan = plan
        ctx.glow_plan.who_gets_what_next = {
            SECRET: "do work",
            f"Claude-{SECRET_TOKEN}": "code",
        }
        ctx.assigned_tasks = [
            AssignedTask(
                assignee=SECRET,
                tasks=["x"],
                blocked_until=f"wait {SECRET}",
            )
        ]
        ctx.flags = [
            {
                "type": f"outdated-{SECRET}",
                "message": f"msg {SECRET}",
                "at": "t",
            }
        ]
        ctx.decisions = ["local-only"]
        store.save_context(ctx)
        return ctx

    def test_scrub_md_flag_type_and_json_assignee_keys(self):
        ctx = self._ctx_with_secrets()
        md_path, json_path, _ = export_handoff(
            ctx, "Claude", out_dir=self.tmp / "out", source=f"Glow {SECRET}"
        )
        md = md_path.read_text(encoding="utf-8")
        js = json_path.read_text(encoding="utf-8")
        data = json.loads(js)
        for label, text in [("md", md), ("json", js)]:
            self.assertNotIn(SECRET, text, label)
            self.assertNotIn("leak-me-please-now", text, label)
        # flag type scrubbed in MD
        self.assertIn("[REDACTED", md)
        # assignee / who keys scrubbed in JSON
        who = (data.get("glow_plan") or {}).get("who_gets_what_next") or {}
        self.assertNotIn(SECRET, json.dumps(who))
        tasks = data.get("assigned_tasks") or []
        self.assertTrue(tasks)
        self.assertNotIn(SECRET, tasks[0].get("assignee", ""))

    def test_manual_packet_metadata_scrubbed(self):
        ctx = self._ctx_with_secrets()
        res = create_manual_packet(
            ctx,
            "claude",
            reason="failed",
            error_class=f"timeout-{SECRET}",
            error_message=f"boom {SECRET_TOKEN}",
            out_dir=self.tmp / "packets",
        )
        text = Path(res.packet_path).read_text(encoding="utf-8")
        self.assertNotIn(SECRET, text)
        self.assertNotIn("leak-me-please-now", text)
        self.assertIn("Error class:", text)
        self.assertIn("Project:", text)
        self.assertIn("Task ID:", text)
        self.assertIn("Version:", text)

    def test_glow_pack_and_context_scrubbed(self):
        ctx = self._ctx_with_secrets()
        result = ResultRecord(
            handoff_id=ctx.current_task_id,
            project=ctx.project,
            based_on_version="1.1.2",
            author="Claude",
            changes=[f"did {SECRET}"],
            verification_evidence=["ok"],
            blockers=[],
            next_action="glow",
        )
        md_path, js_path, _ = write_glow_return_pack(
            ctx, result, out_dir=self.tmp / "glow"
        )
        for p in (md_path, js_path, store.project_dir(ctx.project) / "context.json"):
            text = p.read_text(encoding="utf-8")
            self.assertNotIn(SECRET, text, str(p))
            self.assertNotIn("leak-me-please-now", text, str(p))

    def test_key_collision_from_redaction(self):
        obj = scrub_obj(
            {
                "api_key": "a",
                "token": "b",
                "password": "c",
            },
            root=True,
        )
        # all credential keys collapse toward [REDACTED_KEY] with suffixes
        keys = [k for k in obj if k != "credentials_included"]
        self.assertTrue(all(k.startswith("[REDACTED_KEY]") for k in keys))
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
