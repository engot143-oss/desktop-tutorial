# Brief for Grok Bot — CB-005 → v1.1.2

| Field | Value |
|-------|--------|
| Project | Context Bridge |
| Task ID | CB-005 |
| Based on | Glow FAIL on v1.1.1 @ a354cd061da9b7165473350649684497a899eb7b |
| Target version | **1.1.2** |
| Repo | Local `/workspace/context-bridge` only — **do not push/merge** without Enrique |

## Status
Glow: FAIL until independent re-verify. 26 tests + both demos passed but additional checks failed.

## Required fixes
1. **Repeated round-trip whitespace** — “Who gets what next” gains one newline per cycle (\n → \n\n\n\n after 3). Fix separator handling; compare all four bodies across ≥3 consecutive cycles.
2. **Body fidelity** — CRLF→LF; nested `#### Decisions` truncates Goal. Preserve line endings, indentation, blank lines, continuations, legitimate nested headings; companion sections at correct structural level.
3. **Redaction leaks** — MD flag type; JSON assignee dict key; manual-packet MD project/task ID/version/error class. Scrub all rendered metadata + dict keys; handle key collisions from redaction.
4. **Exact heading titles** — Reject lowercase `goal` and bold `**Goal**`. Literal titles only: Goal, Constraints, Open questions, Who gets what next. Keep supported heading levels; reject altered titles, reorder, duplicates.

## Verification
- Keep existing tests green; add regressions for every failure above.
- Compare all four bodies to independently specified expected values (not same-parser echo).
- Exercise LF and CRLF via real file import/export path.
- Scrub tests: handoffs, manual packets, Glow return packs, persisted context — MD+JSON; full synthetic secret absent everywhere.
- Run full unittest + `demo_round_trip.sh` + `demo_v11_ops.sh`.

## Return package
Changed files + implementation report; exact commands/results/test count; complete verify archive; local commit id if any; remaining blockers. **Do not** mark approved/merged/deployed.

## Constraints
Manual-first, local-only, synthetic secrets only, no live connections. Report before changing the contract.
