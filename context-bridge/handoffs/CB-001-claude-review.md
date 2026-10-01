# Brief for Claude — CB-001 review

| Field | Value |
|-------|--------|
| Project | Context Bridge |
| Task ID | CB-001 |
| Version | 1.0.0 |
| Your role | Reviewer |
| Date | 2026-10-01 (PT) |
| Repo / path | standalone (`/workspace/context-bridge`) |
| Credentials | none — do not add any |
| Implementation status | Build complete; round-trip demo **SUCCEEDED** (Grok Bot) |

Paste this whole brief into Claude. Ask Claude to return a written review in the **Result format** at the bottom so it can be imported back into Context Bridge.

---

## Goal (from Glow — preserved)

Build Context Bridge v1 to carry Glow’s engineering plans to Claude and return results without losing decisions or project context.

## Your assigned tasks

1. Review Grok Bot’s implementation against the original Glow constraints and this brief.
2. Verify a sample Glow four-section plan survives export → import without loss.
3. Verify a follow-up update preserves earlier **decisions** (and does not silently drop assumptions / completion criteria).
4. Confirm result records include changes, verification evidence, blockers, and next action.
5. Confirm conflicting or outdated updates are flagged.
6. Confirm no credentials appear in handoffs; v1 stays local (no auto-send / deploy / repo changes).

**Completion criteria:** Written pass/fail on round-trip fidelity and decision preservation, plus blockers and next action.

---

## What Grok Bot shipped (summary)

Local Python CLI (stdlib only). Claims vs requirements:

| Requirement | Claimed status | Where to look |
|-------------|----------------|---------------|
| Plan import (Goal / Constraints / Open questions / Who gets what next) | Done | `context_bridge/plan_import.py` |
| Saved project context | Done | `context_bridge/store.py` → `data/projects/<slug>/context.json` |
| Recipient handoff export (MD + JSON) | Done | `context_bridge/export.py` |
| Result import (changes, evidence, blockers, next action) | Done | `context_bridge/result_import.py` |
| Flag conflicting / outdated updates | Done | `detect_flags()` in `result_import.py` |
| Working code + README + demonstrated round trip | Done | package + `README.md` + `scripts/demo_round_trip.sh` |

Hard constraints claimed honored: local-only; no credentials (`credentials_included: false`; credential-like keys redacted); no auto-send/deploy/repo changes; Glow’s four sections preserved on export; each handoff records project, repo/path, task ID, version, decisions, assumptions, assigned tasks, completion criteria.

Author’s completion check: sample plan survives export/import **PASS**; follow-up preserves decisions **PASS**; README explains setup + demo **PASS**.

## How to reproduce (for your verification)

```bash
cd /workspace/context-bridge
export PYTHONPATH=/workspace/context-bridge
python3 -m context_bridge --version   # expect Context Bridge 1.0.0
./scripts/demo_round_trip.sh          # full round trip
```

Typical CLI:

```bash
./cb init "My Project"
./cb import-plan "My Project" path/to/glow-plan.md --task-id T-1 --version 1.0.0
./cb export "My Project" "Claude"
./cb import-result "My Project" path/to/result.md --author "Claude"
./cb status "My Project"
```

## Artifacts to inspect

| Artifact | Path |
|----------|------|
| Implementation report | `reports/CB-001-implementation.md` |
| Setup README | `README.md` |
| Round-trip demo script | `scripts/demo_round_trip.sh` |
| Demo outputs | `demos/sample-round-trip/` (incl. `final-context.json`, step logs, `exports/`) |
| CB-001 Claude export | `demos/cb-001-exports/CB-001-claude-v1.0.0.{md,json}` |
| CB-001 Grok Bot export | `demos/cb-001-exports/CB-001-grok-bot-v1.0.0.{md,json}` |
| Original Glow handoff | `handoffs/CB-001-glow-plan.md` + `.json` |

Demo claims to prove: (1) four-section import, (2) Claude + Grok Bot exports keep all four sections + decisions, (3) export → re-import without loss, (4) follow-up merges decisions with `decision_history` snapshot, (5) outdated (0.9.0 vs 1.0.0) and conflict flags raised while earlier decisions remain.

## Original Glow constraints (check against code + demo)

- Start locally with manual paste/import and Markdown + JSON export.
- Preserve Glow’s four-section plan exactly.
- Each handoff records project, repo/path, task ID, version, decisions, assumptions, assigned tasks, and completion criteria.
- Keep credentials out of handoffs. No automatic sending, deployment, or repo changes in v1.

## Decisions already on record (must survive your review cycle)

- Domain default: engineering.
- Context Bridge packages Glow/ChatGPT plans into recipient briefs; Grok Bot owns v1 implementation.
- Claude reviews after a demonstrated round trip exists.
- v1 is local-only; no connectors required for the first ship.

## Result format (return this so Context Bridge can import it)

```markdown
# Result — CB-001 Claude review

## Changes
- [What you inspected / any corrections you recommend]

## Verification evidence
- Round-trip fidelity: PASS | FAIL — [evidence]
- Decision preservation: PASS | FAIL — [evidence]
- Result fields present: PASS | FAIL
- Conflict/outdated flags: PASS | FAIL
- No credentials / local-only: PASS | FAIL

## Blockers
- [None, or list]

## Next action
- [What Enrique / Grok Bot / Glow should do next]

## Decisions
- [Any new decisions from this review; do not drop earlier ones]
```

## Next action for Claude

Review the implementation and demo artifacts above; return the Result block.
