# Live bridge (v1.2)

`cb send` runs one hop when a key or a local model is available. It builds the
worker prompt from the Glow plan, calls a live adapter, saves the reply as a
Result, runs the same import path as `cb import-result`, and writes the Glow
return pack.

If there is no key, no endpoint, or the call fails, it writes the existing
manual `awaiting_execution` packet and saves context. Paste still works.
`cb packet` is unchanged.

Adapters use the Python standard library (`urllib`) only. No vendor SDKs.

## Install

```bash
cd /workspace/context-bridge
python3 -m context_bridge --version   # Context Bridge 1.2.0
pip install ./context-bridge          # installs the `cb` console script
```

The tool itself has no runtime dependencies. `pip` is only for the console script.

## Providers

| Worker | Default provider | Key | Default model | Default endpoint |
|--------|------------------|-----|---------------|------------------|
| `claude` | `anthropic` | `ANTHROPIC_API_KEY` | `claude-3-5-haiku-latest` | `https://api.anthropic.com` |
| `grok` | `xai` | `XAI_API_KEY` | `grok-3-mini` | `https://api.x.ai/v1` |
| `glow`, `chatgpt` | `openai` | `OPENAI_API_KEY` | `gpt-4o-mini` | `https://api.openai.com/v1` |
| any, with `--provider openai-compatible` | OpenAI-compatible | optional | `llama3.2` | `http://localhost:11434/v1` |

`--provider` overrides the default. Aliases `ollama` and `openai-compat` mean
`openai-compatible`. `--model` overrides the model for that call.

Model env vars: `ANTHROPIC_MODEL`, `XAI_MODEL`, `OPENAI_MODEL`,
`OPENAI_COMPAT_MODEL` (or `OLLAMA_MODEL`).

Base URL env vars: `ANTHROPIC_BASE_URL`, `XAI_BASE_URL`, `OPENAI_BASE_URL`,
`OPENAI_COMPAT_BASE_URL` (or `OLLAMA_BASE_URL`). `--base-url` overrides them.
A bare Ollama host such as `http://localhost:11434` is treated as
`http://localhost:11434/v1`. An OpenRouter-style URL that already ends in
`/v1` is left as-is.

## Free path (Ollama)

No key. Install [Ollama](https://ollama.com), pull a small model, and send:

```bash
ollama pull llama3.2
cb send "Habitat Sensors" claude --provider openai-compatible --model llama3.2
```

That uses `http://localhost:11434/v1`. The same adapter talks to any
OpenAI-compatible endpoint, including free or cheap OpenRouter models:

```bash
export OPENAI_COMPAT_BASE_URL=https://openrouter.ai/api/v1
export OPENAI_COMPAT_API_KEY=...          # only if that endpoint requires one
export OPENAI_COMPAT_MODEL=openai/gpt-4o-mini
cb send "Habitat Sensors" grok --provider openai-compatible
```

The optional compat key is `OPENAI_COMPAT_API_KEY` (or `OLLAMA_API_KEY`).
Ollama does not need it.

## Cost and safety

- One attempt. No retries.
- Output cap: `--max-tokens` or `CB_MAX_TOKENS`, default **1024**, hard cap **4096**.
- Timeout: `--timeout` seconds or `CB_TIMEOUT`, default **60**, hard cap **120**.
  Values under 0.1 seconds are raised to 0.1.
- `--dry-run` prints the exact method, URL, redacted headers, and JSON body.
  It does not call the network and does not write a packet or a result.
- API keys are read from the environment only. They are not written to
  packets, results, context, logs, or Glow return packs. Dry-run shows
  `Authorization: Bearer [REDACTED]` or `x-api-key: [REDACTED]`.
- The existing scrub runs on the prompt, the reply, errors, and saved files.
  Known key values are removed even when they do not match the `sk-` pattern.
- Redirects are not followed, so a bearer token is not sent to another host.
- Defaults are the lower-cost model names above. Override them when you want
  a stronger model and accept the price.

## Fallback

| Situation | Connection | Error class | What you get |
|-----------|------------|-------------|--------------|
| Key or endpoint missing | `unavailable` | `connection_unavailable` | Manual packet, exit 3 |
| Timeout, HTTP error, connection error, bad or empty reply | `failed` | `timeout`, `http_error`, `connection_error`, `bad_response`, or `live_call_failed` | Manual packet, exit 3 |
| Call succeeded | `success` | — | Result imported, Glow return pack written, exit 0 |

The packet status stays `awaiting_execution`. Context is saved in every
fallback, including the Glow plan and earlier decisions. A reply that is not
in the official Result shape is still saved: the full text is kept under
Changes, and a missing-evidence flag is reported. An empty reply falls back
instead of importing a blank result.

```bash
cb send "Habitat Sensors" claude
# no ANTHROPIC_API_KEY → packet + "connection: unavailable"
cb send "Habitat Sensors" grok --provider xai --timeout 10
# endpoint down → packet + "connection: failed"
```

## Example loop

Glow writes the four-section plan (Goal / Constraints / Open questions /
Who gets what next). Claude codes. Grok reviews. Each successful hop returns
a Glow pack. Any hop without a key falls back to paste.

```bash
cd /workspace/context-bridge
export PYTHONPATH=/workspace/context-bridge

cb init "Habitat Sensors" --repo .
cb import-plan "Habitat Sensors" plan.md --task-id HAB-1 --version 1.2.0

# Preview the Claude request. Nothing is sent.
cb send "Habitat Sensors" claude --task-id HAB-1 --dry-run

# Claude codes (Anthropic), or a free local stand-in:
cb send "Habitat Sensors" claude --task-id HAB-1
# cb send "Habitat Sensors" claude --provider openai-compatible --model llama3.2

# Grok reviews the updated context.
cb send "Habitat Sensors" grok --task-id HAB-1

# Glow (OpenAI) can be asked for the next plan section the same way:
cb send "Habitat Sensors" glow --task-id HAB-1 --provider openai
```

Each live success prints the Result path and the Glow return pack
(`glow markdown` / `glow json`). Paste that pack back to Glow. If a hop
falls back, paste the manual packet to that worker and run `cb import-result`
as in v1.1.

## Command

```bash
cb send <project> <claude|grok|glow|chatgpt> \
  [--task-id ID] \
  [--provider anthropic|xai|openai|openai-compatible] \
  [--model NAME] \
  [--base-url URL] \
  [--max-tokens N] \
  [--timeout SECONDS] \
  [--dry-run] \
  [--out DIR]
```

`--out` is only the directory for a fallback manual packet.

Exit codes: `0` live success or dry-run, `3` fallback packet saved, `1` the
project or plan is missing (nothing to send), `2` bad arguments.
