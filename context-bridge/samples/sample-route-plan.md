# Handoff ROUTE-001 — Routing sample

| Field | Value |
|-------|--------|
| Project | Route Demo |
| Task ID | ROUTE-001 |
| Version | 1.1.0 |
| Source | Glow |
| Repo / path | /workspace/context-bridge |

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

### Claude — coding
1. Implement route CLI.

**Completion criteria:** route prints worker + reason; ambiguous returns clarify.

### Grok — explore
1. Second opinion on routing defaults.

**Completion criteria:** Written note if asked.
