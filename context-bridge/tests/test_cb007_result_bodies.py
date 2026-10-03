"""CB-007: preserve complete Result bodies (tables, nested headings, fences)."""

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
from context_bridge.glow_pack import (
    build_glow_return_pack,
    render_glow_return_markdown,
    write_glow_return_pack,
)
from context_bridge.models import GlowPlan, ProjectContext, ResultRecord
from context_bridge.result_import import (
    apply_result,
    load_result,
    parse_result_markdown,
)
from context_bridge.scrub import scrub_text

FIXTURE = ROOT / "tests" / "fixtures" / "CB-006-claude-result.md"
OFFICIAL_CB001 = ROOT / "handoffs" / "CB-001-claude-result-v2.md"
SECRET_SK = "sk-aaaaaaaaaaaaaaaaTESTSECRET"
SECRET_PW = "password=supersecret99"


class ParseFullBodiesTests(unittest.TestCase):
    def setUp(self):
        self.text = FIXTURE.read_text(encoding="utf-8")
        self.data = parse_result_markdown(self.text)

    def test_section_bodies_changes_has_table_and_cli(self):
        ch = self.data["section_bodies"]["changes"]
        self.assertIn("|", ch)
        self.assertIn("import-plan", ch)
        self.assertIn("--repo", ch)
        self.assertIn("--replace-decisions", ch)
        self.assertIn("Requirements", ch)
        self.assertIn("Setup", ch)
        self.assertIn("--glow-out", ch)
        self.assertIn("--replace-decisions", ch)

    def test_structured_changes_non_empty(self):
        self.assertGreater(len(self.data["changes"]), 0)

    def test_nested_requirements_not_top_level_section(self):
        keys_lower = {k.lower() for k in self.data["section_bodies"]}
        self.assertNotIn("requirements", keys_lower)
        self.assertNotIn("setup", keys_lower)
        self.assertIn("changes", self.data["section_bodies"])
        # Nested content remains inside Changes
        self.assertIn("## Requirements", self.data["section_bodies"]["changes"])

    def test_heading_inside_fence_does_not_end_changes(self):
        md = """## Changes

Before fence.

```markdown
## Requirements
- stay in changes
## Setup
cd /tmp
```

After fence still changes.
password=not_here_yet

## Verification evidence
- evidence one
"""
        data = parse_result_markdown(md)
        self.assertEqual(
            set(data["section_bodies"].keys()),
            {"changes", "verification_evidence"},
        )
        ch = data["section_bodies"]["changes"]
        self.assertIn("## Requirements", ch)
        self.assertIn("stay in changes", ch)
        self.assertIn("After fence still changes", ch)
        self.assertIn("evidence one", data["verification_evidence"][0])

    def test_duplicate_official_changes_merges_bullets(self):
        md = """## Changes
- alpha item
- beta item

## Changes
- gamma item

## Blockers
- none serious
"""
        data = parse_result_markdown(md)
        self.assertEqual(
            data["changes"],
            ["alpha item", "beta item", "gamma item"],
        )
        body = data["section_bodies"]["changes"]
        self.assertIn("alpha item", body)
        self.assertIn("gamma item", body)
        self.assertIn("duplicate official heading", body)

    def test_raw_markdown_set(self):
        self.assertEqual(self.data["raw_markdown"], self.text)

    def test_near_miss_headings_stay_in_changes(self):
        """Glow FAIL #1: startswith aliases must not open official sections."""
        md = """## Changes

Prose before near-miss headings.

## Blocker examples
- not a real blockers section

## Blocker handling
- also not blockers (startswith trap)

## Next actions proposed
- not a real next action

## New decision examples
- not a real decisions section

Still in changes after near-misses.

## Verification evidence
- real evidence only
"""
        data = parse_result_markdown(md)
        self.assertEqual(
            set(data["section_bodies"].keys()),
            {"changes", "verification_evidence"},
        )
        ch = data["section_bodies"]["changes"]
        self.assertIn("## Blocker examples", ch)
        self.assertIn("## Blocker handling", ch)
        self.assertIn("also not blockers", ch)
        self.assertIn("## Next actions proposed", ch)
        self.assertIn("## New decision examples", ch)
        self.assertIn("not a real blockers section", ch)
        self.assertIn("Still in changes after near-misses", ch)
        self.assertNotIn("blockers", data["section_bodies"])
        self.assertNotIn("next_action", data["section_bodies"])
        self.assertNotIn("decisions", data["section_bodies"])
        self.assertEqual(data["blockers"], [])
        self.assertEqual(data["new_decisions"], [])
        self.assertEqual(data["next_action"], "")
        self.assertEqual(data["verification_evidence"], ["real evidence only"])

    def test_four_tick_fence_ignores_inner_triple_and_decisions(self):
        """Glow FAIL #2: ``` must not close a ```` fence (CommonMark length)."""
        md = """## Changes

Outer prose.

````markdown
Demo snippet:
```
print("hi")

## Decisions
- example decision (must stay in Changes / fence)

## Verification evidence
- example evidence (must stay in fence)
````

After the four-tick fence closes.

## Verification evidence
- real evidence after fence
"""
        data = parse_result_markdown(md)
        self.assertEqual(
            set(data["section_bodies"].keys()),
            {"changes", "verification_evidence"},
        )
        ch = data["section_bodies"]["changes"]
        self.assertIn("## Decisions", ch)
        self.assertIn("example decision (must stay in Changes / fence)", ch)
        self.assertIn("example evidence (must stay in fence)", ch)
        self.assertIn("After the four-tick fence closes", ch)
        self.assertNotIn("decisions", data["section_bodies"])
        self.assertEqual(data["new_decisions"], [])
        self.assertEqual(
            data["verification_evidence"],
            ["real evidence after fence"],
        )
        # Nested shorter fence must not leak: only the outer closer ends it.
        self.assertIn("````markdown", ch)
        self.assertIn("````", ch.split("After the four-tick")[0])


    def test_fenced_bullets_excluded_from_structured_lists(self):
        """Glow FAIL #3: bullets inside fences must not enter structured lists."""
        md = """## Changes

- real change outside fence

```markdown
- fenced change must not be structured
- another fenced change
```

- after fence still structured

## Verification evidence
- real evidence
```
- fenced evidence ignored
```
- evidence after fence

## Blockers
- real blocker
```
- fenced blocker ignored
```

## Decisions
- real decision
```
- fenced decision ignored
```

## Assumptions
- real assumption
```
- fenced assumption ignored
```

## Next action
- do the real next step
```
- fenced next ignored
```
"""
        data = parse_result_markdown(md)
        self.assertEqual(
            data["changes"],
            ["real change outside fence", "after fence still structured"],
        )
        self.assertNotIn("fenced change must not be structured", data["changes"])
        # Full body still preserves fenced bullets for Glow Full Changes.
        ch = data["section_bodies"]["changes"]
        self.assertIn("fenced change must not be structured", ch)
        self.assertEqual(
            data["verification_evidence"],
            ["real evidence", "evidence after fence"],
        )
        self.assertEqual(data["blockers"], ["real blocker"])
        self.assertEqual(data["new_decisions"], ["real decision"])
        self.assertEqual(data["new_assumptions"], ["real assumption"])
        self.assertEqual(data["next_action"], "do the real next step")
        self.assertNotIn("fenced", data["next_action"])


class ScrubBodiesTests(unittest.TestCase):
    def test_secret_in_table_and_fence_scrubbed(self):
        md = f"""## Changes

| Key | Value |
|---|---|
| api | {SECRET_SK} |

```
export TOKEN={SECRET_SK}
{SECRET_PW}
```

- bullet with {SECRET_PW}

## Verification evidence
- ok

## Next action
Ship it.
"""
        tmp = Path(tempfile.mkdtemp(prefix="cb007-scrub-"))
        try:
            path = tmp / "result.md"
            path.write_text(md, encoding="utf-8")
            result = load_result(path)
            self.assertNotIn(SECRET_SK, result.raw_markdown)
            self.assertNotIn("supersecret99", result.raw_markdown)
            self.assertNotIn(SECRET_SK, result.section_bodies.get("changes", ""))
            self.assertNotIn("supersecret99", result.section_bodies.get("changes", ""))
            self.assertIn("[REDACTED_API_KEY]", result.raw_markdown)
            # Structured bullets scrubbed
            joined = " ".join(result.changes)
            self.assertNotIn("supersecret99", joined)

            ctx = ProjectContext(
                project="scrub-unit",
                current_version="1.1.3",
                current_task_id="CB-007",
                decisions=["keep me"],
            )
            pack = build_glow_return_pack(ctx, result)
            pack_s = json.dumps(pack)
            self.assertNotIn(SECRET_SK, pack_s)
            self.assertNotIn("supersecret99", pack_s)
            md_out = render_glow_return_markdown(pack)
            self.assertNotIn(SECRET_SK, md_out)
            self.assertNotIn("supersecret99", md_out)
            self.assertIn("Full Changes (preserved)", md_out)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class CompatOldResultTests(unittest.TestCase):
    def test_from_dict_without_section_bodies(self):
        old = {
            "handoff_id": "OLD-1",
            "project": "p",
            "based_on_version": "1.1.2",
            "author": "Claude",
            "changes": ["only bullet"],
            "verification_evidence": ["ev"],
            "blockers": [],
            "next_action": "go",
            "new_decisions": [],
            "new_assumptions": [],
        }
        rec = ResultRecord.from_dict(old)
        self.assertEqual(rec.raw_markdown, "")
        self.assertEqual(rec.section_bodies, {})
        self.assertEqual(rec.changes, ["only bullet"])

        ctx = ProjectContext(project="compat", current_version="1.1.2")
        pack = build_glow_return_pack(ctx, rec)
        self.assertEqual(pack.get("section_bodies"), {})
        md = render_glow_return_markdown(pack)
        self.assertIn("Full Changes (preserved)", md)
        self.assertIn("only bullet", md)

    def test_glow_pack_missing_section_bodies_key(self):
        """Pack built from result with empty bodies still renders."""
        rec = ResultRecord(
            handoff_id="X",
            project="p",
            based_on_version="1.0",
            author="A",
            changes=["finding one"],
            verification_evidence=["e"],
        )
        ctx = ProjectContext(project="p")
        pack = build_glow_return_pack(ctx, rec)
        self.assertIn("section_bodies", pack)
        md = render_glow_return_markdown(pack)
        self.assertIn("finding one", md)


class DecisionMergeAndOfficialTests(unittest.TestCase):
    def test_decision_merge_appends(self):
        tmp = Path(tempfile.mkdtemp(prefix="cb007-dec-"))
        try:
            original = store.DATA_DIR
            store.DATA_DIR = tmp / "projects"
            store.DATA_DIR.mkdir(parents=True)
            ctx = store.ensure_project("CB007 Decision Pilot")
            ctx.current_task_id = "CB-007"
            ctx.current_version = "1.1.2"
            five = [
                "Pilot project id: cb006-pilot (separate from sample-widget-api).",
                "Based-on version: 1.1.2.",
                "Outcome of this packet step: awaiting_execution only — not completed.",
                "Do not mark pilot completed.",
                "Only import this Result as blocked/logged if desired; full README review still pending.",
            ]
            ctx.decisions = list(five)
            store.save_context(ctx)

            result = load_result(FIXTURE)
            result.author = "Claude"
            result.handoff_id = "CB-006"
            result.based_on_version = "1.1.2"
            ctx, flags = apply_result(ctx, result)
            store.save_context(ctx)

            updated = store.load_context("CB007 Decision Pilot")
            for d in five:
                self.assertIn(d, updated.decisions)
            # Claude's four from the fixture
            self.assertTrue(
                any("Scope held to proposed wording" in d for d in updated.decisions)
            )
            self.assertGreaterEqual(len(updated.decisions), 9)
        finally:
            store.DATA_DIR = original
            shutil.rmtree(tmp, ignore_errors=True)

    def test_load_official_cb001_still_works(self):
        self.assertTrue(OFFICIAL_CB001.exists())
        result = load_result(OFFICIAL_CB001)
        self.assertGreaterEqual(len(result.new_decisions), 4)
        self.assertIn("Grok Bot:", result.next_action)
        self.assertIn("changes", result.section_bodies)
        self.assertTrue(result.raw_markdown)


class GlowPackFullChangesTests(unittest.TestCase):
    def test_glow_pack_contains_table_and_readme_wording(self):
        result = load_result(FIXTURE)
        ctx = ProjectContext(
            project="cb007-glow",
            current_version="1.1.3",
            current_task_id="CB-006",
            decisions=["Pilot project id: cb006-pilot (separate from sample-widget-api)."],
            repo_path="/workspace/context-bridge",
        )
        pack = build_glow_return_pack(ctx, result)
        md = render_glow_return_markdown(pack)
        self.assertIn("## Full Changes (preserved)", md)
        self.assertIn("| Command | Gap |", md)
        self.assertIn("--replace-decisions", md)
        self.assertIn("## Requirements", md)
        self.assertIn("## Setup", md)
        self.assertIn("--glow-out", md)
        self.assertIn("import-plan", md)
        # JSON pack carries bodies
        self.assertIn("changes", pack["section_bodies"])
        self.assertIn("|", pack["section_bodies"]["changes"])


if __name__ == "__main__":
    unittest.main()
