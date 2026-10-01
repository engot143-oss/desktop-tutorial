#!/usr/bin/env bash
# Context Bridge v1 — demonstrated round trip
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
CB=(python3 -m context_bridge)
DEMO="$ROOT/demos/sample-round-trip"
rm -rf "$DEMO"
mkdir -p "$DEMO"
# Fresh sample project data (do not wipe other projects)
SAMPLE_DATA="$ROOT/data/projects/sample-widget-api"
rm -rf "$SAMPLE_DATA"

echo "=== 1. Init project ==="
"${CB[@]}" init "Sample Widget API" | tee "$DEMO/01-init.txt"

echo "=== 2. Validate + import Glow plan ==="
"${CB[@]}" validate-plan samples/sample-glow-plan.md | tee "$DEMO/02-validate.txt"
"${CB[@]}" import-plan "Sample Widget API" samples/sample-glow-plan.md \
  --task-id SAMPLE-001 --version 1.0.0 | tee "$DEMO/03-import-plan.txt"

echo "=== 3. Export for Claude and Grok Bot ==="
"${CB[@]}" export "Sample Widget API" "Claude" --out "$DEMO/exports" | tee "$DEMO/04-export-claude.txt"
"${CB[@]}" export "Sample Widget API" "Grok Bot" --out "$DEMO/exports" | tee "$DEMO/05-export-grok.txt"

echo "=== 4. Prove four sections survived in Claude export ==="
CLAUDE_MD=$(ls "$DEMO/exports"/SAMPLE-001-claude-*.md | head -1)
python3 - << PY | tee "$DEMO/06-section-check.txt"
from pathlib import Path
text = Path("$CLAUDE_MD").read_text()
needed = ["### Goal", "### Constraints", "### Open questions", "### Who gets what next"]
missing = [h for h in needed if h not in text]
assert not missing, f"Missing sections: {missing}"
assert "Ship a minimal read-only Widget API stub" in text
assert "Domain default: engineering." in text
print("PASS: four Glow sections + sample goal + decisions present in", "$CLAUDE_MD")
PY

echo "=== 5. Re-import exported Markdown (round-trip fidelity) ==="
# Use a scratch project to prove export→import without clobbering live context
"${CB[@]}" init "Sample Roundtrip Check" | tee "$DEMO/07-rt-init.txt"
"${CB[@]}" import-plan "Sample Roundtrip Check" "$CLAUDE_MD" \
  --task-id SAMPLE-001 --version 1.0.0 | tee "$DEMO/08-rt-import.txt"
python3 - << PY | tee "$DEMO/09-rt-fidelity.txt"
import json
from pathlib import Path
ctx = json.loads(Path("$ROOT/data/projects/sample-roundtrip-check/context.json").read_text())
plan = ctx["glow_plan"]
assert plan["goal"]
assert len(plan["constraints"]) >= 4
assert "Claude" in str(plan["who_gets_what_next"]) or any("Claude" in k for k in plan["who_gets_what_next"])
assert "Domain default: engineering." in ctx["decisions"]
print("PASS: exported Markdown re-imported; goal/constraints/who/decisions intact")
PY

echo "=== 6. Import result into live sample project ==="
"${CB[@]}" import-result "Sample Widget API" samples/sample-result.md \
  --author "Grok Bot" | tee "$DEMO/10-import-result.txt"

echo "=== 7. Follow-up update — decisions must survive ==="
BEFORE=$(python3 -c "import json; from pathlib import Path; c=json.loads(Path('$ROOT/data/projects/sample-widget-api/context.json').read_text()); print(len(c['decisions']))")
"${CB[@]}" import-result "Sample Widget API" samples/sample-followup-result.md \
  --author "Grok Bot" | tee "$DEMO/11-followup.txt"
python3 - << PY | tee "$DEMO/12-decision-preserve.txt"
import json
from pathlib import Path
ctx = json.loads(Path("$ROOT/data/projects/sample-widget-api/context.json").read_text())
needed = [
    "Domain default: engineering.",
    "v1 is local-only.",
    "Four-section Glow shape is canonical.",
    "Demo artifacts live under demos/sample-round-trip/.",
    "Follow-up updates must merge decisions, never silently drop them.",
]
missing = [d for d in needed if d not in ctx["decisions"]]
assert not missing, f"Missing decisions: {missing}"
assert any(h.get("event") == "pre_result_snapshot" for h in ctx["decision_history"])
before = int("$BEFORE")
print(f"PASS: all {len(needed)} decisions present (had {before} before follow-up); history snapshotted")
PY

echo "=== 8. Outdated + conflicting result should flag ==="
"${CB[@]}" import-result "Sample Widget API" samples/sample-outdated-result.md \
  --author "External Agent" | tee "$DEMO/13-flags.txt"
python3 - << PY | tee "$DEMO/14-flag-check.txt"
import json
from pathlib import Path
ctx = json.loads(Path("$ROOT/data/projects/sample-widget-api/context.json").read_text())
types = {f["type"] for f in ctx["flags"]}
assert "outdated" in types, types
assert "conflict" in types, types
# Earlier decisions still present despite conflicting new decision being recorded
assert "v1 is local-only." in ctx["decisions"]
print("PASS: outdated + conflict flags raised; earlier decisions still preserved")
print("Flags:")
for f in ctx["flags"]:
    print(f"  [{f['type']}] {f['message']}")
PY

# Copy context snapshot into demo folder
cp "$ROOT/data/projects/sample-widget-api/context.json" "$DEMO/final-context.json"
cp samples/sample-glow-plan.md "$DEMO/"

echo ""
echo "=== ROUND TRIP DEMO SUCCEEDED ==="
echo "Artifacts: $DEMO"
