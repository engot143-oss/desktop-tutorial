# CB-003 — Context Bridge v1.1 build brief (for Glow)

## Goal
Implement Eric’s hierarchy: Eric → Glow (lead) → Grok Bot (execution orchestrator) → Claude (coding) / Grok (explore / second opinion), with preserved task IDs, decisions, and context; clear failed-call and missing-evidence reporting; manual handoff packets when a connection is unavailable.

## Constraints
- Local-first CLI remains source of truth on disk under `/workspace/context-bridge`
- No credentials in handoffs; scrub credential-like keys
- No auto-deploy or unsolicited repo changes
- Preserve Glow’s four sections exactly: Goal / Constraints / Open questions / Who gets what next
- Each handoff records: project, repo/path, task ID, version, decisions, assumptions, assigned tasks, completion criteria
- If a live connection isn’t available → produce manual handoff packet marked `awaiting_execution`

## Open questions
- Which authorized Claude / Grok connection paths does Eric want first (API, Cursor cloud, paste-only stub)?
- Default project/repo path once named

## Who gets what next
- **Glow:** Own this brief; confirm routing defaults and connection priority; return updated plan if anything changes
- **Grok Bot (execution):** Implement v1.1 slices below after Glow signs off
- **Claude:** Coding worker for adapter + CLI changes when assigned
- **Grok:** Exploration / second-opinion worker when assigned
- **Eric:** Approve scope and connection choices

## Defaults (assumptions until Glow overrides)
- Claude = coding; Grok = exploration / second opinion
- Glow may reassign per task via Who gets what next
- Manual paste remains the fallback path

---

## Already shipped (v1.0.2) — do not rebuild
- Plan import (four sections)
- Saved project context
- Recipient export (Markdown + JSON)
- Result import (changes, evidence, blockers, next action, decisions)
- Conflict / outdated flags; task ID + version preservation
- Round-trip demo + regression tests
- Context Bridge bot for packaging briefs in chat

## Build (v1.1)

### Slice A — Router
Parse Who gets what next → `recipient: claude | grok` (and later glow/eric).
CLI: `route --task-id …` prints chosen worker + reason; Glow can override.

### Slice B — Glow return pack
After `import-result`, emit Glow-facing summary:
- findings, verification evidence, blockers, next action
- preserved decisions + task ID + based-on-version
- open flags (conflict / outdated / missing evidence / failed call)

### Slice C — Connection adapters
Authorized call-outs to Claude and Grok supplying context + instructions.
On success: ingest worker result into result-import contract.
On failure or no connection: write manual packet with status `awaiting_execution` and report failed call clearly (worker, error class, task ID, packet path).

### Slice D — Context Bridge bot ops
Bot owns: receive Glow handoff → route → call or packet → return Glow pack.
Grok Bot remains execution orchestrator; bot does not replace CLI.

## Completion criteria
- Sample Glow plan routes Claude vs Grok correctly by default and on override
- Result import still preserves decisions across a follow-up
- Failed connection produces `awaiting_execution` packet + clear failure report
- Glow return pack is enough for Glow to check work and assign next step without re-asking for prior context
- README documents Eric → Glow → Grok Bot → worker loop

## Out of scope for v1.1
- Auto-send into ChatGPT/Glow UI
- Deploy pipelines, credential vaults, multi-repo sync

## Suggested Glow response format
Keep the four sections; under Who gets what next assign Slice A–D owners and any connection choice (live vs stub).
