# Claude — CB-002 unblock instructions

1. Download and extract `CB-001-claude-artifact-pack.tgz`.
2. From the extract root: `export PYTHONPATH=$PWD` then `./scripts/demo_round_trip.sh` (needs Python 3.10+).
3. Inspect `context_bridge/export.py` and `result_import.py`.
4. **Exact preservation:** export a plan and check Goal/Constraints/Open questions/Who gets what next for title spelling, order, and whitespace — not just presence.
5. **Free-text secrets:** import a plan or result that plants a fake token in an assumption/result note (value field, not a key named token). Confirm whether it is redacted or leaks in MD/JSON exports. Report PASS/FAIL with evidence.
6. Return the Result block (Changes / Verification evidence / Blockers / Next action / Decisions). Do not drop earlier decisions; review status may move from pending verification to pass or fail.
