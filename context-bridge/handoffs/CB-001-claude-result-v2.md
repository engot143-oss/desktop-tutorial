# Result — CB-001 Claude review

## Changes
- Inspected: CB-001-glow-plan, CB-001-claude-v1.0.0 (.md/.json), final-context.json, export.py, result_import.py, 13-flags.txt, 14-flag-check.txt. Not seen: store.py, models.py, plan_import.py, CLI, README, demo script, implementation report, Grok Bot export.
- Ran result_import.parse_result_markdown against the Result template from this brief (stubbed imports, parser unchanged).
- Recommended fixes are listed under Blockers and Non-blocking issues.

## Verification evidence
- Round-trip fidelity: PASS (content) — Goal, 5 constraints, open question, and all 3 "who gets what next" entries match the original text. Decisions (4) and assumptions (3) are identical. Formatting is not byte-exact (see N1–N4).
- Decision preservation: PASS (earlier decisions) — the merge is append-only and never removes. final-context.json holds 6 decisions with the first 4 intact. 3 decision_history snapshots exist, each a strict subset of the next. Caveat: new decisions in the official Result format are dropped (B1).
- Result fields present: PASS (records) — demo result stored changes=1, evidence=1, blockers=1, next_action set. Importer enforcement is weak (N6) and next_action parsing is lossy (B2).
- Conflict/outdated flags: PASS (demo scenarios) — the 0.9.0 vs 1.0.0 "outdated" flag and the "remote connectors vs v1 is local-only" conflict flag both fired, and earlier decisions remained. Limits: see N5 and N7.
- No credentials / local-only: PASS (partial scope) — no secret-like strings in any pack file. export.py and result_import.py import only json, re, pathlib, datetime, and the package's own models/store, so no network or subprocess calls. Caveats: credentials_included is hard-coded False in export.py, not computed, and the redaction code was not in the pack.

## Blockers
- B1: The importer only recognizes headings starting "new decision" or "decisions added". The official Result format uses "## Decisions", so decisions from any review are silently dropped. The template has no meta table, so based_on_version, author, and task ID are empty and the outdated and task-mismatch checks are skipped. Fix: accept "Decisions" and "New decisions", and add --based-on-version and --task-id CLI flags as fallbacks.
- B2: next_action keeps only the first line and keeps the "- " prefix. Tested: a two-bullet Next action imported as "- Eric: attach files, then re-run." and the second bullet was lost. Fix: strip bullet markers and join all bullets.

## Non-blocking issues
- N1: The "Completion criteria" line is swallowed into the last numbered task, then printed twice in the export (both the Claude export and the sample context).
- N2: The JSON export puts "credentials_included": false inside who_gets_what_next as if it were a recipient. This will break a clean JSON re-import.
- N3: The Open questions paragraph becomes a "- " bullet on export.
- N4: Provenance is narrowed on export. "Source: Glow (via Enrique paste)" becomes "Context Bridge", and the repo note "pending Enrique target folder/repo" becomes "standalone".
- N5: export.py never reads ctx.flags, so recipients don't see open flags. A flagged conflicting decision is still appended to active decisions, so "v1 is local-only" and "allow remote connectors" are both active.
- N6: Import only requires changes, evidence, or next action. Blockers are not required, which does not match the spec.
- N7: The conflict heuristic only triggers on decisions starting "no"/"not" or containing "instead of". It will miss a plain "Allow cloud sync in v1."

## Next action
- Grok Bot: fix B1 and B2. Add a regression test that imports the official Result template and asserts new decisions, task ID, and the full next action are captured. Re-run the demo, then address N1, N2, and N5.
- Enrique: send the remaining files (store.py, models.py, plan_import.py, CLI, README, demo_round_trip.sh, reports/CB-001-implementation.md, Grok Bot export) so I can finish the redaction and local-only review.
- Glow: hold CB-001 as "conditional pass" until B1 and B2 are closed and re-reviewed.

## Decisions
- CB-001 review status: conditional pass, pending B1 and B2.
- The official Result format is the import contract. The importer must conform to it, not the other way around.
- Conflicting or outdated updates must be flagged in recipient exports, not only in stored context.
- Earlier decisions stay on record, unchanged: engineering default domain; Context Bridge packages plans into recipient briefs and Grok Bot owns v1; Claude reviews after a demonstrated round trip; v1 is local-only with no connectors.
