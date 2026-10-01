# Brief for Claude — CB-003 review (Context Bridge v1.1.0)

| Field | Value |
|-------|--------|
| Project | Context Bridge |
| Task ID | CB-003 |
| Version | 1.1.0 |
| Your role | Reviewer (optional coding follow-ups if Glow assigns) |
| Repo / path | Extract `CB-003-claude-review-pack.tgz` → folder `context-bridge/` (README, scripts/, context_bridge/, FOR_CLAUDE/). |
| Credentials | none — do not add any |

## Goal
Verify v1.1 slices A–D against the Glow brief and implementation report. Confirm baseline v1.0.2 still holds (B1/B2 Result-contract fixes) and that scrubbing covers free-text secrets.

## What to verify
1. **Baseline:** `python3 -m unittest tests.test_result_import_official` and `./scripts/demo_round_trip.sh` — `## Decisions` and multi-bullet Next action must import correctly.
2. **Slice A:** `cb route` picks claude vs grok; `--override` wins; ambiguous → exit 2 + clarify.
3. **Slice B:** After `import-result`, Glow pack has findings, evidence, blockers, next action, decisions, task ID, based-on-version, open flags.
4. **Slice C:** Manual adapters; `awaiting_execution`; unavailable vs failed are distinct flags/packets.
5. **Slice D:** README documents Enrique → Glow → Grok Bot → worker; CLI is source of truth.
6. **Scrub:** Plant a fake secret in a free-text assumption/evidence value; MD + JSON export must not leak it. Key-name scrub alone is not enough.
7. **Four sections:** titles and order preserved on export (note any whitespace/`- ` prefix drift).

## How to run
```bash
# after extract — cd into context-bridge/
cd context-bridge
export PYTHONPATH=$PWD
python3 -m context_bridge --version   # 1.1.0
python3 -m unittest tests.test_result_import_official tests.test_v11_slices -v
./scripts/demo_round_trip.sh
./scripts/demo_v11_ops.sh
```

## Key paths
`reports/CB-003-implementation.md`, `README.md`, `context_bridge/route.py`, `glow_pack.py`, `adapters/manual.py`, `scrub.py`, `cli.py`, `tests/test_v11_slices.py`, `scripts/demo_v11_ops.sh`, `demos/v11-ops/`

## Result format (return this)
```markdown
# Result — CB-003 Claude review

## Changes
- 

## Verification evidence
- Baseline (B1/B2 / round-trip): PASS | FAIL —
- Slice A route: PASS | FAIL —
- Slice B Glow pack: PASS | FAIL —
- Slice C adapters: PASS | FAIL —
- Slice D ops/README: PASS | FAIL —
- Free-text scrub: PASS | FAIL —
- Four-section preservation: PASS | FAIL —

## Blockers
- 

## Next action
- 

## Decisions
- 
```
