"""Regression tests for the v1.2 QA fixes. No network."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from context_bridge import store
from context_bridge.adapters.anthropic import AnthropicAdapter
from context_bridge.adapters.manual import create_manual_packet
from context_bridge.adapters.transport import require_http_url, resolve_timeout
from context_bridge.cli import main
from context_bridge.glow_pack import build_glow_return_pack, write_glow_return_pack
from context_bridge.live_send import _write_reply
from context_bridge.models import GlowPlan, ResultRecord
from context_bridge.result_import import apply_result

PLAN = ROOT / "samples" / "sample-route-plan.md"
RESULT = ROOT / "samples" / "sample-result.md"


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = StringIO(), StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue(), err.getvalue()


class QABase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cb-qa-"))
        self.outside = self.tmp / "outside"
        self.outside.mkdir()
        self._orig = store.DATA_DIR
        store.DATA_DIR = self.tmp / "projects"
        self._open_guard = patch(
            "context_bridge.adapters.transport._open",
            side_effect=AssertionError("unexpected network call"),
        )
        self._open_guard.start()

    def tearDown(self):
        self._open_guard.stop()
        store.DATA_DIR = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, argv: list[str]) -> tuple[int, str, str]:
        code, out, err = _run(argv)
        self.assertNotIn("Traceback", out + err, out + err)
        return code, out, err

    def project(self, name: str = "QA Proj", task: str = "QA-1") -> None:
        code, out, err = self.cli(
            ["import-plan", name, str(PLAN), "--task-id", task, "--version", "1.2.0"]
        )
        self.assertEqual(code, 0, out + err)

    def assert_outside_clean(self) -> None:
        leaked = [p for p in self.outside.rglob("*") if p.is_file()]
        self.assertEqual(leaked, [], f"wrote outside the project: {leaked}")


class PathTraversalTests(QABase):
    def test_packet_task_id_cannot_escape_or_persist(self):
        self.project()
        code, out, err = self.cli(
            [
                "packet",
                "QA Proj",
                "claude",
                "--task-id",
                "../../../outside/PWNED",
            ]
        )
        self.assertEqual(code, 1, out + err)
        self.assertIn("ERROR:", err)
        self.assertIn("safe file name", err)
        self.assert_outside_clean()
        ctx = store.load_context("QA Proj")
        self.assertEqual(ctx.current_task_id, "QA-1")
        self.assertFalse(any(self.tmp.rglob("PWNED*")))

    def test_plan_task_id_and_version_cannot_escape(self):
        self.project()
        bad = self.tmp / "bad-plan.md"
        text = PLAN.read_text(encoding="utf-8")
        text = text.replace("| Task ID | ROUTE-001 |", "| Task ID | ../../../outside/PWNED |")
        text = text.replace("| Version | 1.1.0 |", "| Version | ../../../outside/V |")
        bad.write_text(text, encoding="utf-8")
        code, out, err = self.cli(["import-plan", "QA Proj", str(bad)])
        self.assertEqual(code, 1, out + err)
        self.assertIn("ERROR:", err)
        self.assertIn("safe file name", err)
        ctx = store.load_context("QA Proj")
        self.assertEqual(ctx.current_task_id, "QA-1")
        self.assertEqual(ctx.current_version, "1.2.0")
        # A safe --task-id still wins over a bad row, and a bad --version is refused.
        code, out, err = self.cli(
            ["import-plan", "QA Proj", str(bad), "--task-id", "QA-2", "--version", "1.2.1"]
        )
        self.assertEqual(code, 0, out + err)
        self.assertEqual(store.load_context("QA Proj").current_task_id, "QA-2")

    def test_export_recipient_cannot_escape(self):
        self.project()
        for recipient in ("../../../outside/evil", "a/b", "../../evil"):
            code, out, err = self.cli(["export", "QA Proj", recipient])
            self.assertEqual(code, 1, out + err)
            self.assertIn("ERROR:", err)
            self.assert_outside_clean()
        code, out, err = self.cli(["export", "QA Proj", "Claude"])
        self.assertEqual(code, 0, out + err)
        root = store.project_dir("QA Proj").resolve()
        written = [p for p in root.rglob("*") if p.is_file()]
        self.assertTrue(any(p.parent.name == "exports" and p.suffix == ".md" for p in written))
        for path in written:
            self.assertTrue(path.resolve().is_relative_to(root), path)

    def test_result_and_glow_pack_task_id_cannot_escape(self):
        self.project()
        bad = self.tmp / "bad-result.md"
        text = RESULT.read_text(encoding="utf-8").replace(
            "| Task ID | SAMPLE-001 |", "| Task ID | ../../../outside/PWNED |"
        )
        bad.write_text(text, encoding="utf-8")
        code, out, err = self.cli(["import-result", "QA Proj", str(bad)])
        self.assertEqual(code, 1, out + err)
        self.assertIn("ERROR:", err)
        self.assert_outside_clean()
        ctx = store.load_context("QA Proj")
        ctx.current_task_id = "../../../outside/PWNED"
        store.save_context(ctx)
        code, out, err = self.cli(["glow-pack", "QA Proj"])
        self.assertEqual(code, 1, out + err)
        self.assertIn("ERROR:", err)
        self.assertIn("safe file name", err)
        self.assert_outside_clean()

    def test_absolute_task_id_is_not_written(self):
        self.project()
        sentinel = self.tmp / "abs-pwned.md"
        code, _out, err = self.cli(
            ["packet", "QA Proj", "claude", "--task-id", str(sentinel)]
        )
        self.assertEqual(code, 1)
        self.assertIn("ERROR:", err)
        self.assertFalse(sentinel.exists())


class NameAndSlugTests(QABase):
    def test_empty_and_punctuation_names_are_rejected(self):
        for name in ("", "///", "...", "???", "!!"):
            code, out, err = self.cli(["init", name])
            self.assertEqual(code, 1, f"{name!r}: {out}{err}")
            self.assertIn("ERROR:", err)
            self.assertIn("letter or digit", err)
        self.assertFalse((store.DATA_DIR / "project").exists())
        code, out, err = self.cli(["init", "A"])
        self.assertEqual(code, 0, out + err)
        self.project()
        for recipient in ("", "...", "???"):
            code, out, err = self.cli(["export", "QA Proj", recipient])
            self.assertEqual(code, 1, f"{recipient!r}: {out}{err}")
            self.assertIn("ERROR:", err)
            self.assertIn("letter or digit", err)

    def test_slug_collision_is_refused(self):
        code, out, err = self.cli(["init", "Route Demo"])
        self.assertEqual(code, 0, out + err)
        code, out, err = self.cli(["init", "Route Demo"])
        self.assertEqual(code, 0, out + err)
        for other in ("route-demo", "route_demo", "ROUTE DEMO"):
            code, out, err = self.cli(["init", other])
            self.assertEqual(code, 1, f"{other}: {out}{err}")
            self.assertIn("ERROR:", err)
            self.assertIn("Route Demo", err)
            self.assertIn("same folder", err)
        code, out, err = self.cli(["status", "route-demo"])
        self.assertEqual(code, 1, out + err)
        self.assertIn("Route Demo", err)
        code, out, err = self.cli(["status"])
        self.assertEqual(code, 0, out + err)
        self.assertIn("Route Demo", out)
        self.assertNotIn("route-demo", out)
        ctx = store.load_context("Route Demo")
        self.assertEqual(ctx.project, "Route Demo")


class BaseUrlAndTimeoutTests(QABase):
    def test_file_and_ftp_base_urls_are_rejected_on_dry_run_and_send(self):
        self.project()
        for scheme_url in ("file:///etc/passwd", "ftp://x", "FILE:///etc/passwd"):
            for extra in (["--dry-run"], []):
                code, out, err = self.cli(
                    [
                        "send",
                        "QA Proj",
                        "claude",
                        "--provider",
                        "openai-compatible",
                        "--base-url",
                        scheme_url,
                        *extra,
                    ]
                )
                self.assertEqual(code, 1, f"{scheme_url} {extra}: {out}{err}")
                self.assertIn("ERROR:", err)
                self.assertIn("http or https", err)
                self.assertNotIn("would_send", out)
        code, out, err = self.cli(
            [
                "send",
                "QA Proj",
                "claude",
                "--provider",
                "openai-compatible",
                "--base-url",
                "http://127.0.0.1:9/v1",
                "--dry-run",
            ]
        )
        self.assertEqual(code, 0, out + err)
        self.assertIn("would_send=yes", out)
        self.assertIn("http://127.0.0.1:9/v1", out)
        with self.assertRaises(ValueError):
            require_http_url("file:///etc/passwd")
        self.assertEqual(require_http_url("https://api.anthropic.com"), "https://api.anthropic.com")

    def test_non_finite_timeouts_are_rejected(self):
        self.project()
        for raw in ("nan", "inf", "NaN", "-inf"):
            code, out, err = self.cli(
                ["send", "QA Proj", "grok", f"--timeout={raw}", "--dry-run"]
            )
            self.assertEqual(code, 2, f"{raw}: {out}{err}")
            self.assertIn("finite", (err + out).lower())
        with patch.dict("os.environ", {"CB_TIMEOUT": "nan"}):
            code, out, err = self.cli(["send", "QA Proj", "grok", "--dry-run"])
        self.assertEqual(code, 1, out + err)
        self.assertIn("ERROR:", err)
        self.assertIn("finite", err)
        with self.assertRaises(ValueError):
            resolve_timeout(float("nan"))
        with self.assertRaises(ValueError):
            resolve_timeout(float("inf"))
        seconds, note = resolve_timeout(-1)
        self.assertEqual(seconds, 0.1)
        self.assertIsNone(note)
        code, out, err = self.cli(
            ["send", "QA Proj", "grok", "--timeout", "10", "--dry-run"]
        )
        self.assertEqual(code, 0, out + err)
        self.assertIn("timeout_s=10", out)


class FriendlyErrorTests(QABase):
    def test_unknown_project_is_one_line_error(self):
        commands = [
            ["export", "Nope Proj", "Claude"],
            ["route", "Nope Proj"],
            ["packet", "Nope Proj", "claude"],
            ["import-result", "Nope Proj", str(RESULT)],
            ["glow-pack", "Nope Proj"],
            ["status", "Nope Proj"],
        ]
        for argv in commands:
            code, out, err = self.cli(argv)
            self.assertEqual(code, 1, f"{argv}: {out}{err}")
            self.assertTrue(err.startswith("ERROR:"), err)
            self.assertIn("Nope Proj", err)
            self.assertNotIn("\n", err.strip())

    def test_validate_plan_missing_binary_and_directory(self):
        code, out, err = self.cli(["validate-plan", str(self.tmp / "missing.md")])
        self.assertEqual(code, 1, out + err)
        self.assertIn("ERROR:", err)
        self.assertIn("file not found", err)
        binary = self.tmp / "binary.md"
        binary.write_bytes(b"\xff\xfe not text")
        code, out, err = self.cli(["validate-plan", str(binary)])
        self.assertEqual(code, 1, out + err)
        self.assertIn("not valid UTF-8", err)
        code, out, err = self.cli(["import-plan", "QA Proj", str(binary)])
        self.assertEqual(code, 1, out + err)
        self.assertIn("ERROR:", err)
        self.assertIn("not valid UTF-8", err)
        code, out, err = self.cli(["import-plan", "QA Proj", str(self.tmp)])
        self.assertEqual(code, 1, out + err)
        self.assertIn("directory", err)
        code, out, err = self.cli(["validate-plan", str(self.tmp)])
        self.assertEqual(code, 1, out + err)
        self.assertIn("directory", err)
        self.project()
        code, out, err = self.cli(["import-result", "QA Proj", str(binary)])
        self.assertEqual(code, 1, out + err)
        self.assertIn("not valid UTF-8", err)

    def test_result_json_errors_are_one_line(self):
        self.project()
        cases = {
            "bad.json": '{',
            "list.json": "[1, 2]",
            "obj.json": '{"author": 1, "changes": ["x"], "next_action": "y"}',
            "changes.json": '{"changes": 5, "next_action": "y"}',
        }
        for name, body in cases.items():
            path = self.tmp / name
            path.write_text(body, encoding="utf-8")
            for argv in (
                ["import-result", "QA Proj", str(path)],
                ["glow-pack", "QA Proj", "--result", str(path)],
            ):
                code, out, err = self.cli(argv)
                self.assertEqual(code, 1, f"{argv}: {out}{err}")
                self.assertTrue(err.startswith("ERROR:"), err)
                self.assertNotIn("\n", err.strip())


class LimitAndPackTests(QABase):
    def test_input_size_limit(self):
        self.project()
        over = self.tmp / "over.md"
        over.write_bytes(b"a" * (store.MAX_INPUT_BYTES + 1))
        code, out, err = self.cli(["import-plan", "Huge Proj", str(over), "--task-id", "H-1"])
        self.assertEqual(code, 1, out + err)
        self.assertIn("ERROR:", err)
        self.assertIn("1 MiB", err)
        self.assertFalse((store.DATA_DIR / "huge-proj").exists())
        code, _out, err = self.cli(["import-result", "QA Proj", str(over)])
        self.assertEqual(code, 1)
        self.assertIn("1 MiB", err)
        at_limit = self.tmp / "limit.md"
        at_limit.write_bytes(b"a" * store.MAX_INPUT_BYTES)
        code, _out, err = self.cli(["validate-plan", str(at_limit)])
        self.assertEqual(code, 1)
        self.assertIn("INVALID:", err)
        self.assertNotIn("1 MiB", err)

    def test_claude_default_model(self):
        self.assertEqual(AnthropicAdapter().default_model, "claude-haiku-4-5")
        self.assertEqual(AnthropicAdapter().model, "claude-haiku-4-5")

    def test_missing_evidence_is_not_double_counted(self):
        self.project()
        ctx = store.load_context("QA Proj")
        result = ResultRecord(
            handoff_id="QA-1",
            project="QA Proj",
            based_on_version="1.2.0",
            author="Claude",
            changes=["did the work"],
            verification_evidence=[],
            blockers=[],
            next_action="Glow reviews",
        )
        ctx, flags = apply_result(ctx, result)
        self.assertEqual(sum(1 for f in flags if f["type"] == "missing_evidence"), 1)
        self.assertEqual(
            sum(1 for f in ctx.flags if f["type"] == "missing_evidence"), 1
        )
        pack = build_glow_return_pack(ctx, result)
        self.assertEqual(pack["flag_summary"]["missing_evidence"], 1)
        self.assertEqual(
            sum(1 for f in pack["open_flags"] if f.get("type") == "missing_evidence"),
            1,
        )
        # A pack built before import still reports the gap once.
        fresh = store.load_context("QA Proj")
        # apply_result saved nothing; reload is the pre-import context.
        # The in-memory ctx above is not what load returns unless saved.
        lone = build_glow_return_pack(fresh, result)
        self.assertEqual(lone["flag_summary"]["missing_evidence"], 1)

    def test_same_stamp_does_not_overwrite(self):
        self.project()
        ctx = store.load_context("QA Proj")
        ctx.glow_plan = ctx.glow_plan or GlowPlan(goal="x")
        with patch(
            "context_bridge.store.filename_stamp",
            return_value="20260101T000000000000Z",
        ):
            first = create_manual_packet(ctx, "claude")
            second = create_manual_packet(ctx, "claude")
            g1, _j1, _p1 = write_glow_return_pack(ctx, out_dir=None)
            g2, _j2, _p2 = write_glow_return_pack(ctx, out_dir=None)
            live1 = _write_reply(ctx, "claude", "one")
            live2 = _write_reply(ctx, "claude", "two")
        paths = [
            Path(first.packet_path),
            Path(second.packet_path),
            g1,
            g2,
            live1,
            live2,
        ]
        self.assertEqual(len({p.resolve() for p in paths}), len(paths))
        for path in paths:
            self.assertTrue(path.is_file(), path)
            self.assertTrue(path.resolve().is_relative_to(store.project_dir("QA Proj").resolve()))
        self.assertNotEqual(live1.read_text(encoding="utf-8"), live2.read_text(encoding="utf-8"))
        self.assertIn("-2", Path(second.packet_path).name)


if __name__ == "__main__":
    unittest.main()
