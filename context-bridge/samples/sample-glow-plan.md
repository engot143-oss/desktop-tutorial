# Handoff SAMPLE-001 — Sample Widget API

| Field | Value |
|-------|--------|
| Project | Sample Widget API |
| Task ID | SAMPLE-001 |
| Version | 1.0.0 |
| Source | Glow (sample) |
| Date | 2026-10-01 |
| Repo / path | standalone |
| Credentials | none — keep out of all exports |

## Glow plan (preserved)

### Goal
Ship a minimal read-only Widget API stub that returns a hard-coded list of widgets for local demos.

### Constraints
- Local only; manual paste/import of plans and results.
- Preserve Glow’s four-section plan exactly.
- No credentials in handoffs.
- No auto-send, deploy, or repo changes in this sample.
- Python stdlib only for the stub consumer.

### Open questions
- None blocking. Assume standalone until a target folder/repo is named.

### Who gets what next
- **Claude:** Review the exported handoff and confirm four sections survived intact.
- **Grok Bot:** Implement the stub, export a recipient brief, import a result, and prove decisions survive a follow-up update.
- **Enrique:** Optional — name a target folder/repo when ready.

## Decisions
- Domain default: engineering.
- v1 is local-only.
- Four-section Glow shape is canonical.

## Assumptions
- Standalone project path until a folder/repo is named.
- Recipients consume Markdown + JSON by manual paste.

## Assigned tasks

### Grok Bot — build
1. Import this sample plan.
2. Export briefs for Claude and Grok Bot.
3. Import a result and a follow-up update.
4. Show that earlier decisions are preserved.

**Completion criteria:** Sample plan survives export/import; follow-up preserves decisions; flags appear on outdated/conflicting updates.

### Claude — review
1. Verify four-section fidelity.
2. Verify decision preservation.

**Completion criteria:** Written pass/fail on fidelity and preservation.
