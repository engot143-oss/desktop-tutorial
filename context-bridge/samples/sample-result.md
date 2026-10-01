# Result — SAMPLE-001

| Field | Value |
|-------|--------|
| Project | Sample Widget API |
| Task ID | SAMPLE-001 |
| Based on version | 1.0.0 |
| Author | Grok Bot |

## Changes
- Created local Context Bridge project context for Sample Widget API.
- Exported recipient handoffs (Markdown + JSON) for Claude and Grok Bot.
- Documented round-trip steps in demos/.

## Verification evidence
- `cb validate-plan samples/sample-glow-plan.md` exits 0.
- Exported Claude brief still contains Goal / Constraints / Open questions / Who gets what next.
- Re-import of exported Markdown round-trips without dropping decisions.

## Blockers
- None.

## Next action
Claude reviews the exported brief; Enrique optionally names a target folder/repo.

## New decisions
- Demo artifacts live under demos/sample-round-trip/.
