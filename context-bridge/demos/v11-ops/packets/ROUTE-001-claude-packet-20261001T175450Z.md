# Manual packet — ROUTE-001 for Claude

**Status:** `awaiting_execution`
**Connection:** `unavailable` (no live link)
**Worker:** claude
**Adapter:** manual
**Error class:** connection_unavailable
**Error message:** No authorized live connection; manual paste packet prepared.

## Instructions
You are the Claude worker under hierarchy Eric → Glow → Grok Bot → Claude (coding) / Grok (explore).
Execute the assigned work. Return a Result using the official format:
Changes / Verification evidence / Blockers / Next action / Decisions.
Paste the Result back for `cb import-result`.

## Handoff (scrubbed)

# Handoff ROUTE-001 — Ops Flow Demo (for Claude)

| Field | Value |
|-------|--------|
| Project | Ops Flow Demo |
| Task ID | ROUTE-001 |
| Version | 1.1.0 |
| Recipient | Claude |
| Date | 2026-10-01 |
| Source | Context Bridge manual adapter |
| Repo / path | /workspace/context-bridge |
| Credentials | none — keep out of all exports |

## Glow plan (preserved)
### Goal
Demonstrate Claude vs Grok routing from Who gets what next with Glow override.

### Constraints
- Local-only; manual paste adapters first.
- Preserve four sections exactly.
- No credentials in handoffs.

### Open questions
- None blocking for the routing demo.

### Who gets what next
- **Claude:** Implement the router CLI and coding fixes for Context Bridge.
- **Grok:** Explore alternative routing heuristics and give a second opinion.
- **Grok Bot:** Orchestrate execution; do not replace Claude/Grok workers.
- **Glow:** Override worker assignment when needed.
- **Eric:** Approve scope.


## Decisions
- Claude = coding default; Grok = explore / second opinion.
- Glow override beats defaults.

## Assumptions
- Manual paste until Eric authorizes live connections.

## Assigned tasks

### Claude
1. Implement route CLI.

**Completion criteria:** route prints worker + reason; ambiguous returns clarify.

## Open flags
- (none)

## Next action
Implement the router CLI and coding fixes for Context Bridge.


---
After execution, return a Result Markdown and run:
`cb import-result "Ops Flow Demo" path/to/result.md --task-id ROUTE-001 --based-on-version 1.1.0`
