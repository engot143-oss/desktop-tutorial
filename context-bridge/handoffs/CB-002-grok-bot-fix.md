# Brief for Grok Bot — CB-002 fix B1/B2

| Field | Value |
|-------|--------|
| Project | Context Bridge |
| Task ID | CB-002 |
| Version | 1.0.1 → 1.0.2 expected |
| Source | Claude conditional-pass review |

## Must fix now
**B1:** `result_import` only matches headings starting "new decision" or "decisions added". Official Result uses `## Decisions`, so new decisions are silently dropped. Also empty meta → outdated/task-mismatch checks skipped. Accept "Decisions" and "New decisions"; add `--based-on-version` and `--task-id` CLI flags.

**B2:** `next_action` keeps only first line and keeps "- " prefix. Strip bullets; join all bullets/lines.

## Required regression
Import the official Result template from `handoffs/CB-001-claude-result-v2.md` (or equivalent fixture) and assert: new decisions captured, task ID set when provided, full multi-bullet next_action preserved.

## Then
Re-run `./scripts/demo_round_trip.sh`. Address N1, N2, N5 from Claude’s list. Full detail: `handoffs/CB-001-claude-result-v2.md`.

## Constraints
Local-only; no credentials; preserve existing decisions; Result format is the import contract.

## Completion criteria
B1/B2 closed with regression green; demo re-run; report path for Enrique → Claude re-review.
