# Context Bridge v1.2

Local engineering handoff tool. Carry Glow plans to workers (Claude / Grok)
and bring results back to Glow without losing decisions or project context.

v1.2 has three ways to run a hop:

- **Manual copy-paste** (`cb packet`) — writes an `awaiting_execution` packet. Paste still works, and it is the fallback when a live hop cannot run.
- **Local Ollama** — `cb send` with `--provider openai-compatible` talks to `http://localhost:11434/v1` (default model `llama3.2`). No API key.
- **Optional direct APIs** — `cb send` can call Claude (`ANTHROPIC_API_KEY`), ChatGPT / Glow (`OPENAI_API_KEY`), or Grok (`XAI_API_KEY`) with the user's own keys. One attempt; keys stay in the environment.

The `cb` command is the CLI (`./cb` in this tree, or `cb` after `pip install`). Details: [docs/LIVE-BRIDGE.md](docs/LIVE-BRIDGE.md).

**Hierarchy:** Eric → Glow (lead) → Grok Bot (execution) → Claude (coding default) /
Grok (explore / second opinion)

**Hard rules:** paste remains the fallback · no credentials in handoffs · scrub keys **and**
free-text patterns before export · no auto-send / deploy · Glow’s four sections
preserved (Goal / Constraints / Open questions / Who gets what next) · CLI is
authoritative on disk under `/workspace/context-bridge`

## Requirements

- Python 3.10+ (stdlib only — no runtime dependencies)
- `pip` is only needed to install the `cb` console script

## Setup

```bash
cd /workspace/context-bridge
export PYTHONPATH=/workspace/context-bridge
python3 -m context_bridge --version   # Context Bridge 1.2.0
# or: ./cb --version
pip install .                         # installs the `cb` console script
```

## Ops flow (Slice D) — CLI authoritative

```
receive Glow plan  →  route worker  →  manual packet  →  worker executes (paste)
        ↑                                                        ↓
   Glow return pack  ←  import-result (flags + decisions)  ←  Result Markdown
```

```bash
# 1) Receive
./cb init "My Project" --repo /workspace/context-bridge
./cb import-plan "My Project" path/to/glow-plan.md --task-id T-1 --version 1.2.0

# 2) Route (ambiguous → exit 2 / clarify; Glow --override wins)
./cb route "My Project" --task-id T-1
./cb route "My Project" --task-id T-1 --role coding
./cb route "My Project" --task-id T-1 --override claude

# 3) Manual packet (copy-paste; also the fallback packet shape)
./cb packet "My Project" claude --reason unavailable
# If a live call was attempted and failed:
./cb packet "My Project" grok --reason failed --error-class timeout --error-message "…"

# 3b) One live hop (Ollama, or Claude/ChatGPT/Grok with your own key).
# Missing key, missing endpoint, or a failed call writes the manual packet.
./cb send "My Project" claude --dry-run
./cb send "My Project" claude --provider openai-compatible --model llama3.2

# 4) After worker pastes back a Result:
./cb import-result "My Project" path/to/result.md --author Claude
# → also writes Glow return pack (findings, evidence, blockers, next action,
#    decisions, task ID, based-on-version, all open flags)

# 5) Or emit Glow pack explicitly:
./cb glow-pack "My Project" --result path/to/result.md
```

Distinguish connection outcomes:

| Situation | `--reason` | Packet status | Flag type |
|-----------|------------|---------------|-----------|
| Key or endpoint missing | `unavailable` | `awaiting_execution` | `connection_unavailable` |
| Live call attempted, failed | `failed` | `awaiting_execution` | `failed_call` |

Open flags reported explicitly: `conflict`, `outdated`, `missing_evidence`,
`failed_call`, `connection_unavailable`.

## Glow plan shape (required)

Exact section titles, in order:

1. **Goal**
2. **Constraints**
3. **Open questions**
4. **Who gets what next**

Optional companions: Decisions, Assumptions, Assigned tasks.

## CLI reference

```bash
./cb init "Name" [--repo path]
./cb import-plan "Name" plan.md [--task-id ID] [--version V]
./cb export "Name" "Claude|Grok Bot|…"
./cb route "Name" [--task-id ID] [--role coding|explore] [--override claude|grok]
./cb packet "Name" claude|grok [--reason unavailable|failed] …
./cb send "Name" claude|grok|glow|chatgpt [--provider …] [--model …] [--dry-run]
./cb import-result "Name" result.md [--author A] [--task-id ID] [--based-on-version V]
./cb glow-pack "Name" [--result result.md]
./cb status ["Name"]
./cb validate-plan plan.md
```

## Demos & tests

```bash
# Classic round-trip (v1 decisions / export-import)
./scripts/demo_round_trip.sh

# Ops loop (route → packet → Glow return)
./scripts/demo_v11_ops.sh

# Unit tests (no API keys)
python3 -m unittest discover -s tests
```

## Project layout

```
context-bridge/
  cb / README.md
  context_bridge/
    cli.py              # authoritative CLI
    route.py            # Slice A
    glow_pack.py        # Slice B
    adapters/manual.py  # manual paste packet
    adapters/           # anthropic, xai, openai, openai-compatible (Ollama)
    live_send.py        # cb send: one hop, else manual packet
    scrub.py            # key + free-text redaction
    plan_import.py / export.py / result_import.py / store.py / models.py
  data/projects/<slug>/ # context, exports, packets, glow_returns, results
  samples/ scripts/ tests/ demos/ handoffs/ reports/
```

## What v1.2 does *not* do

- No automatic send into the ChatGPT or Glow UI (use `cb send`, or paste the packet)
- No Cursor cloud calls, deploy pipelines, credential vaults, or multi-repo sync
- No retries: one live attempt, then the manual packet

## CB-004 (v1.1.2)

- Exact four-section contract: reject reorder/alter/duplicate; preserve section body whitespace.
- Scrub free-text secrets on all export surfaces including metadata and Blocked until.
- Regression: `python3 -m unittest tests.test_cb004_fidelity_scrub -v`

## CB-005 (v1.1.2)

- Stable multi-cycle four-section body fidelity; CRLF preserved.
- Nested #### headings stay in body; companion stops at #/## only.
- Literal titles only; scrub dict keys + all metadata surfaces.
- Status remains FAIL until Glow re-verifies.
