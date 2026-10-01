# Handoff CB-001 — Context Bridge (for Claude)

| Field | Value |
|-------|--------|
| Project | Context Bridge |
| Task ID | CB-001 |
| Version | 1.0.0 |
| Recipient | Claude |
| Date | 2026-10-01 |
| Source | Context Bridge |
| Repo / path | standalone |
| Credentials | none — keep out of all exports |

## Glow plan (preserved)

### Goal
Grok Bot, build Context Bridge v1 to carry Glow’s engineering plans to Claude and return results without losing decisions or project context.

### Constraints
- Start locally with manual paste/import and Markdown + JSON export.
- Preserve Glow’s four-section plan exactly.
- Each handoff records project, repo/path, task ID, version, decisions, assumptions, assigned tasks, and completion criteria.
- Keep credentials out of handoffs. No automatic sending, deployment, or repo changes in v1.
- No deadline specified.

### Open questions
- None blocking. Assume a standalone project until Enrique supplies a target folder or repo.

### Who gets what next
- **Claude:** Review Grok Bot’s implementation. Verify a sample plan survives export/import and follow-up updates preserve earlier decisions.
- **Grok Bot / Context Bridge:** Build plan import, saved project context, recipient-specific handoff export, and result import. Results must include changes, verification evidence, blockers, and next action. Flag conflicting or outdated updates. Deliver working code, setup README, and one demonstrated round trip.
- **Enrique:** Paste this specification to Grok Bot and bring its implementation report back to Glow for review.

## Decisions
- Domain default: engineering.
- Context Bridge packages Glow/ChatGPT plans into recipient briefs; Grok Bot owns v1 implementation.
- Claude reviews after a demonstrated round trip exists.
- v1 is local-only; no connectors required for the first ship.

## Assumptions
- Standalone project path until Enrique names a folder/repo.
- “Claude” may be an external chat; no Claude teammate is connected in this workspace yet.
- Four-section Glow shape (Goal / Constraints / Open questions / Who gets what next) is the canonical plan schema.

## Assigned tasks

### Claude
1. Review implementation against this handoff.
2. Verify sample plan survives export/import.
3. Verify follow-up updates preserve earlier decisions. **Completion criteria:** Written review noting pass/fail on round-trip fidelity and decision preservation, plus any blockers or next actions.

**Completion criteria:** Written review noting pass/fail on round-trip fidelity and decision preservation, plus any blockers or next actions.

## Next action
Review Grok Bot’s implementation. Verify a sample plan survives export/import and follow-up updates preserve earlier decisions.
