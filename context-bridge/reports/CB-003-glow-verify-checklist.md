# Glow verify checklist — CB-003 Context Bridge v1.1.0

Use this with the pack `handoffs/CB-003-v1.1.0-verify-pack.tgz` and
`reports/CB-003-verify-output.txt` (all three runs captured; expect
`ALL_THREE_SUCCEEDED=YES`).

## Hierarchy (confirm understanding)
Eric → Glow (lead) → Grok Bot (execution) → Claude (coding default) / Grok (explore / 2nd opinion).  
CLI under `/workspace/context-bridge` is authoritative. Live connections out of scope until Eric authorizes. Manual packets = `awaiting_execution`.

## What to check

### 1. Exact four-section shape
- [ ] Imported Glow plans require **Goal / Constraints / Open questions / Who gets what next** (exact titles, that order).
- [ ] Exports still render those four headings in order (see `export.py` / sample exports in demos if present).
- [ ] Whitespace inside section bodies should survive import→export for content fidelity (titles/order required; note any byte-level whitespace drift you care about).

### 2. Decision preservation
- [ ] Follow-up `import-result` **merges** decisions; earlier ones stay (demo round-trip + ops demo).
- [ ] Official Result `## Decisions` is accepted (not only “New decisions”) — regression in `tests.test_result_import_official`.

### 3. Multi-bullet next_action
- [ ] Result `## Next action` with multiple bullets is joined (all bullets kept; leading `- ` stripped) — assert in official Result regression.

### 4. Routing overrides
- [ ] `cb route` with both Claude + Grok assigned and **no** `--role` → status `clarify` (exit 2).
- [ ] `--role coding` → Claude; `--role explore` → Grok.
- [ ] `--override claude|grok` **wins** over role/defaults (Glow override) — see `demo_v11_ops.sh` / `tests.test_v11_slices.RouteTests`.

### 5. Unavailable vs failed packets
- [ ] `cb packet … --reason unavailable` → packet `awaiting_execution`, underlying `unavailable`, flag `connection_unavailable`.
- [ ] `cb packet … --reason failed` → packet `awaiting_execution`, underlying `failed`, flag `failed_call` (distinct from unavailable).
- [ ] Packets and exports scrub credential-like **keys** and **free-text** patterns (no secrets in handoffs).

### 6. Glow return pack (Slice B)
- [ ] After `import-result`, pack includes: findings, verification evidence, blockers, next action, decisions, task ID, based-on-version, **all open flags** (conflict / outdated / missing_evidence / failed_call / connection_unavailable).

### 7. Captured runs (this package)
- [ ] `reports/CB-003-verify-output.txt` shows:
  - unit tests: `Ran 18 tests` → `OK`
  - `=== ROUND TRIP DEMO SUCCEEDED ===`
  - `=== V1.1 OPS DEMO SUCCEEDED ===`
  - `ALL_THREE_SUCCEEDED=YES`

## How to re-verify from the pack

```bash
tar -xzf CB-003-v1.1.0-verify-pack.tgz
cd context-bridge
export PYTHONPATH="$PWD"
python3 -m unittest tests.test_result_import_official tests.test_v11_slices -v
./scripts/demo_round_trip.sh
./scripts/demo_v11_ops.sh
```

## Pass / fail for Glow
- **PASS** if checklist items hold and captured output matches `ALL_THREE_SUCCEEDED=YES`.
- **FAIL** if any required section/routing/packet distinction is wrong, decisions drop, or verification capture is missing/red.
