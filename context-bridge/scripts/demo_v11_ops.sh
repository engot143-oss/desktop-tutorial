#!/usr/bin/env bash
# Context Bridge v1.1 — ops loop demo: receive → route → packet → import → Glow return
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
CB=(python3 -m context_bridge)
DEMO="$ROOT/demos/v11-ops"
rm -rf "$DEMO"
mkdir -p "$DEMO"
# Isolate this demo's project data
rm -rf "$ROOT/data/projects/ops-flow-demo"

echo "=== receive (import Glow plan) ==="
"${CB[@]}" init "Ops Flow Demo" --repo /workspace/context-bridge | tee "$DEMO/01-init.txt"
"${CB[@]}" import-plan "Ops Flow Demo" samples/sample-route-plan.md \
  --task-id ROUTE-001 --version 1.1.0 | tee "$DEMO/02-import-plan.txt"

echo "=== route (ambiguous then Glow override) ==="
set +e
"${CB[@]}" route "Ops Flow Demo" --task-id ROUTE-001 | tee "$DEMO/03-route-ambiguous.txt"
AMB=$?
set -e
test "$AMB" -eq 2
"${CB[@]}" route "Ops Flow Demo" --task-id ROUTE-001 --override claude | tee "$DEMO/04-route-override.txt"

echo "=== packet (manual awaiting_execution) ==="
"${CB[@]}" packet "Ops Flow Demo" claude --reason unavailable --out "$DEMO/packets" \
  | tee "$DEMO/05-packet.txt"

echo "=== import worker result → Glow return ==="
cat > "$DEMO/worker-result.md" << 'RES'
# Result — ROUTE-001

| Field | Value |
|-------|--------|
| Project | Ops Flow Demo |
| Task ID | ROUTE-001 |
| Based on version | 1.1.0 |
| Author | Claude |

## Changes
- Verified route + manual packet path for v1.1.

## Verification evidence
- scripts/demo_v11_ops.sh green

## Blockers
- None.

## Next action
- Glow checks return pack and assigns next step.

## Decisions
- Ops loop stays CLI-authoritative; live adapters deferred until Eric authorizes.
RES

"${CB[@]}" import-result "Ops Flow Demo" "$DEMO/worker-result.md" \
  --author Claude --glow-out "$DEMO/glow" | tee "$DEMO/06-import-glow.txt"

python3 - << PY | tee "$DEMO/07-checks.txt"
import json
from pathlib import Path
pack = json.loads(Path("$DEMO/glow/latest.json").read_text())
assert pack["task_id"] == "ROUTE-001"
assert pack["based_on_version"] == "1.1.0"
assert any("CLI-authoritative" in d or "Glow override" in d for d in pack["decisions"])
assert pack.get("open_flags") is not None
pkt = next(Path("$DEMO/packets").glob("*.md"))
text = pkt.read_text()
assert "awaiting_execution" in text
print("PASS: Glow return pack + awaiting_execution packet OK")
print("decisions:", len(pack["decisions"]), "flags:", len(pack["open_flags"]))
PY

echo ""
echo "=== V1.1 OPS DEMO SUCCEEDED ==="
echo "Artifacts: $DEMO"
