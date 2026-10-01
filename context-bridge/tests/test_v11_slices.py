"""CB-003 v1.1 — slices A (route), B (glow pack), C (manual packet), scrub."""

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
from context_bridge.cli import main as cli_main
from context_bridge.glow_pack import build_glow_return_pack, write_glow_return_pack
from context_bridge.models import GlowPlan, ProjectContext, ResultRecord
from context_bridge.plan_import import import_plan_file
from context_bridge.route import route_task
from context_bridge.scrub import scrub_obj, scrub_text


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cb-route-"))
        self._orig = store.DATA_DIR
        store.DATA_DIR = self.tmp / "projects"

    def tearDown(self):
        store.DATA_DIR = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _load_plan(self, name: str, project: str, task_id: str) -> ProjectContext:
        ctx = store.ensure_project(project, repo_path="/workspace/context-bridge")
        ctx = import_plan_file(
            ROOT / "samples" / name,
            ctx,
            task_id=task_id,
            version="1.1.0",
        )
        store.save_context(ctx)
        return store.load_context(project)

    def test_both_workers_ambiguous_without_role(self):
        ctx = self._load_plan("sample-route-plan.md", "Route Demo", "ROUTE-001")
        d = route_task(ctx, task_id="ROUTE-001")
        self.assertEqual(d.status, "clarify")
        self.assertIsNone(d.worker)
        self.assertIn("claude", d.candidates)
        self.assertIn("grok", d.candidates)

    def test_role_coding_selects_claude(self):
        ctx = self._load_plan("sample-route-plan.md", "Route Demo", "ROUTE-001")
        d = route_task(ctx, role="coding")
        self.assertEqual(d.status, "ok")
        self.assertEqual(d.worker, "claude")

    def test_role_explore_selects_grok(self):
        ctx = self._load_plan("sample-route-plan.md", "Route Demo", "ROUTE-001")
        d = route_task(ctx, role="explore")
        self.assertEqual(d.status, "ok")
        self.assertEqual(d.worker, "grok")

    def test_glow_override_wins(self):
        ctx = self._load_plan("sample-route-plan.md", "Route Demo", "ROUTE-001")
        d = route_task(ctx, override="grok", role="coding")
        self.assertEqual(d.status, "ok")
        self.assertEqual(d.worker, "grok")
        self.assertTrue(d.override_applied)
        self.assertIn("Glow override", d.reason)

    def test_sole_claude(self):
        ctx = self._load_plan(
            "sample-claude-only-plan.md", "Route Demo Claude", "ROUTE-002"
        )
        d = route_task(ctx)
        self.assertEqual(d.status, "ok")
        self.assertEqual(d.worker, "claude")
        # Grok Bot must not be treated as Grok worker
        self.assertNotIn("grok", d.candidates)

    def test_cli_route_override(self):
        self._load_plan("sample-route-plan.md", "Route Demo", "ROUTE-001")
        rc = cli_main(
            ["route", "Route Demo", "--task-id", "ROUTE-001", "--override", "claude"]
        )
        self.assertEqual(rc, 0)


class GlowPackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cb-glow-"))
        self._orig = store.DATA_DIR
        store.DATA_DIR = self.tmp / "projects"

    def tearDown(self):
        store.DATA_DIR = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_glow_pack_fields(self):
        ctx = store.ensure_project("Glow Pack Demo")
        ctx.current_task_id = "GP-1"
        ctx.current_version = "1.1.0"
        ctx.decisions = ["v1 is local-only.", "Glow override beats defaults."]
        ctx.flags = [
            {"type": "outdated", "message": "stale", "at": "t"},
            {"type": "conflict", "message": "clash", "at": "t"},
        ]
        result = ResultRecord(
            handoff_id="GP-1",
            project="Glow Pack Demo",
            based_on_version="1.0.2",
            author="Claude",
            changes=["Did the thing"],
            verification_evidence=["tests green"],
            blockers=["None."],
            next_action="Glow assigns next step",
            new_decisions=[],
        )
        pack = build_glow_return_pack(ctx, result)
        for key in (
            "findings",
            "verification_evidence",
            "blockers",
            "next_action",
            "decisions",
            "task_id",
            "based_on_version",
            "open_flags",
        ):
            self.assertIn(key, pack)
        self.assertEqual(pack["task_id"], "GP-1")
        self.assertEqual(pack["based_on_version"], "1.0.2")
        self.assertGreaterEqual(len(pack["open_flags"]), 2)
        self.assertIn("v1 is local-only.", pack["decisions"])
        md, js, _ = write_glow_return_pack(ctx, result, out_dir=self.tmp / "out")
        self.assertTrue(md.exists())
        self.assertTrue(js.exists())
        body = md.read_text()
        self.assertIn("## Findings", body)
        self.assertIn("## Open flags", body)
        self.assertIn("[outdated]", body)

    def test_missing_evidence_flag_on_pack(self):
        ctx = store.ensure_project("Missing Ev")
        ctx.current_task_id = "ME-1"
        ctx.decisions = ["keep"]
        result = ResultRecord(
            handoff_id="ME-1",
            project="Missing Ev",
            based_on_version="1.1.0",
            author="Claude",
            changes=["x"],
            verification_evidence=[],
            blockers=[],
            next_action="y",
        )
        pack = build_glow_return_pack(ctx, result)
        types = {f["type"] for f in pack["open_flags"]}
        self.assertIn("missing_evidence", types)


class ManualPacketTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cb-pkt-"))
        self._orig = store.DATA_DIR
        store.DATA_DIR = self.tmp / "projects"

    def tearDown(self):
        store.DATA_DIR = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self) -> ProjectContext:
        ctx = store.ensure_project("Packet Demo", repo_path="/workspace/context-bridge")
        ctx.current_task_id = "PKT-1"
        ctx.current_version = "1.1.0"
        ctx.decisions = ["manual-first"]
        ctx.glow_plan = GlowPlan(
            goal="Ship packet",
            constraints=["local only"],
            open_questions=["None."],
            who_gets_what_next={
                "Claude": "Implement adapters",
                "Grok": "Second opinion on adapter shape",
            },
        )
        store.save_context(ctx)
        return ctx

    def test_unavailable_packet(self):
        ctx = self._ctx()
        res = create_manual_packet(ctx, "claude", reason="unavailable")
        store.save_context(ctx)
        self.assertEqual(res.status.value, "awaiting_execution")
        self.assertEqual(res.details["underlying"], "unavailable")
        self.assertTrue(Path(res.packet_path).exists())
        text = Path(res.packet_path).read_text()
        self.assertIn("awaiting_execution", text)
        self.assertIn("unavailable", text)
        types = {f["type"] for f in ctx.flags}
        self.assertIn("connection_unavailable", types)
        data = json.loads(
            next((store.project_dir(ctx.project) / "packets").glob("*.json")).read_text()
        )
        self.assertEqual(data["status"], "awaiting_execution")
        self.assertFalse(data.get("live_adapter_ready"))

    def test_failed_call_distinct_from_unavailable(self):
        ctx = self._ctx()
        res = create_manual_packet(
            ctx,
            "grok",
            reason="failed",
            error_class="timeout",
            error_message="upstream timeout api_key=SECRET123 sk-abcdefghijklmnopqrstuvwxyz",
        )
        store.save_context(ctx)
        self.assertEqual(res.details["underlying"], "failed")
        types = {f["type"] for f in ctx.flags}
        self.assertIn("failed_call", types)
        text = Path(res.packet_path).read_text()
        self.assertIn("failed", text)
        # Free-text scrub
        self.assertNotIn("SECRET123", text)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz", text)


class ScrubTests(unittest.TestCase):
    def test_free_text_patterns(self):
        raw = "use token=abc123 and Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xx and sk-abcdefghijklmnopqrstuv"
        out = scrub_text(raw)
        self.assertNotIn("abc123", out)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xx", out)
        self.assertIn("[REDACTED", out)

    def test_nested_keys_root_flag_only(self):
        obj = scrub_obj(
            {
                "who_gets_what_next": {"Claude": "do work", "password": "nope"},
                "note": "api_key=visible-secret",
            },
            root=True,
        )
        self.assertEqual(obj["credentials_included"], False)
        self.assertNotIn("credentials_included", obj["who_gets_what_next"])
        # CB-005: credential-named keys are renamed to [REDACTED_KEY]
        who = obj["who_gets_what_next"]
        self.assertNotIn("password", who)
        self.assertIn("[REDACTED_KEY]", who)
        self.assertEqual(who["[REDACTED_KEY]"], "[REDACTED]")
        self.assertNotIn("visible-secret", obj["note"])


class OpsFlowCliTests(unittest.TestCase):
    """Slice D smoke: receive → route → packet → (result) → glow pack."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cb-ops-"))
        self._orig = store.DATA_DIR
        store.DATA_DIR = self.tmp / "projects"

    def tearDown(self):
        store.DATA_DIR = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ops_loop(self):
        rc = cli_main(
            [
                "init",
                "Ops Demo",
                "--repo",
                "/workspace/context-bridge",
            ]
        )
        self.assertEqual(rc, 0)
        rc = cli_main(
            [
                "import-plan",
                "Ops Demo",
                str(ROOT / "samples" / "sample-route-plan.md"),
                "--task-id",
                "ROUTE-001",
                "--version",
                "1.1.0",
            ]
        )
        self.assertEqual(rc, 0)
        # Ambiguous without role → exit 2
        rc = cli_main(["route", "Ops Demo", "--task-id", "ROUTE-001"])
        self.assertEqual(rc, 2)
        rc = cli_main(
            ["route", "Ops Demo", "--task-id", "ROUTE-001", "--override", "claude"]
        )
        self.assertEqual(rc, 0)
        rc = cli_main(
            [
                "packet",
                "Ops Demo",
                "claude",
                "--reason",
                "unavailable",
                "--out",
                str(self.tmp / "packets"),
            ]
        )
        self.assertEqual(rc, 0)
        # Fake worker result
        result_path = self.tmp / "worker-result.md"
        result_path.write_text(
            """# Result — ROUTE-001

| Field | Value |
|-------|--------|
| Project | Ops Demo |
| Task ID | ROUTE-001 |
| Based on version | 1.1.0 |
| Author | Claude |

## Changes
- Implemented route + packet path.

## Verification evidence
- unittest green

## Blockers
- None.

## Next action
- Glow reviews return pack.

## Decisions
- Manual adapters remain default until Eric authorizes live links.
""",
            encoding="utf-8",
        )
        rc = cli_main(
            [
                "import-result",
                "Ops Demo",
                str(result_path),
                "--author",
                "Claude",
                "--glow-out",
                str(self.tmp / "glow"),
            ]
        )
        self.assertEqual(rc, 0)
        latest = self.tmp / "glow" / "latest.json"
        self.assertTrue(latest.exists())
        pack = json.loads(latest.read_text())
        self.assertEqual(pack["task_id"], "ROUTE-001")
        self.assertTrue(
            any("Manual adapters" in d for d in pack["decisions"]),
            pack["decisions"],
        )
        # Earlier decision preserved
        self.assertTrue(any("Glow override" in d for d in pack["decisions"]))


if __name__ == "__main__":
    unittest.main()
