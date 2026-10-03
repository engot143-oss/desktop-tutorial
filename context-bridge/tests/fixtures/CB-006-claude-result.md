## Changes

**1. Incorrect or incomplete commands (README vs. real CLI)**

No README command contradicts the CLI. All nine subcommands exist and the version string matches. The problems are omitted flags and a few claims the help can't confirm.

| Command | Gap |
|---|---|
| `import-plan` | README omits `--repo` and `--replace-decisions` (default is merge/preserve) |
| `route` | README omits `--json` |
| `packet` | README's `…` hides `--task-id`, `--error-class`, `--error-message`, `--instructions`, `--out` |
| `import-result` | README omits `--glow-out` and `--no-glow-pack`. The CLI also accepts a Markdown **or JSON** result file, while the README says only `result.md` |
| `glow-pack` | README omits `--task-id`, `--based-on-version`, `--out` |
| `export`, `status`, `validate-plan` | Cannot be compared (see Blockers) |

Claims the help dump neither confirms nor contradicts:
- The README table calls `--reason unavailable` the "(default)", but the help states no default.
- "ambiguous → exit 2" is not in the help. Argparse also uses exit code 2 for usage errors, so the README should say how to tell the two apart.
- `python3 -m context_bridge --version` is not shown. The help only shows the `cb` entry point.

**2. Missing prerequisites**
- `/workspace/context-bridge` must already exist, and `./cb` must be executable.
- Whether `./cb` needs `PYTHONPATH` is unstated. The `export` line is shown only for `python3 -m`.
- Order dependency: `init` must come before `import-plan`, and `import-plan` before `route`. `route` reads the plan's "Who gets what next" section.
- The same `--task-id` and project name must be used across steps. The README doesn't say how project names map to the `data/projects/<slug>/` folder.
- `import-result` expects the official Result Markdown (`Changes`, `Verification evidence`, `Blockers`, `Next action`, `Decisions`). This is implied by the Glow-pack contents but never stated as the required shape.

**3. Unclear manual handoff steps**
- `packet` never says where the file is written (`--out`) or what the human does with it.
- The diagram's "worker executes (paste)" doesn't say who pastes what, or into which tool.
- Step 5 overlaps step 4, since `import-result` already writes the Glow return pack. The README doesn't say when to use `glow-pack` separately.
- The README never says where the Glow return pack lands (`--glow-out`) or that it is carried to Glow by manual paste.
- `export` vs. `packet`: no guidance on when to use which. Recipient naming also differs between "Grok Bot" (`export`) and `grok` (`route` and `packet`).
- CB-005's "Status remains FAIL until Glow re-verifies" doesn't say what is failing or who clears it.

**Proposed README wording (wording only, no repo edits)**

*Replace "Requirements" and "Setup":*
```markdown
## Requirements

- Python 3.10+ (standard library only, no pip packages)
- A checkout at `/workspace/context-bridge` with `./cb` executable

## Setup

cd /workspace/context-bridge
export PYTHONPATH=/workspace/context-bridge
./cb --version   # expect: Context Bridge 1.1.2
```

*Add under "Ops flow":*
```markdown
Run the steps in order, using the same project name and `--task-id` throughout.
Nothing is sent anywhere automatically; you carry each file by hand.

1. Receive: `init`, then `import-plan` (optionally `validate-plan` first).
2. Route: `route` picks `claude` or `grok`. If it cannot decide, it stops and
   asks you to choose; re-run with `--role` or `--override`.
3. Packet: `packet` writes an `awaiting_execution` file (folder set by `--out`).
   Open it and paste its contents into the worker's chat yourself.
4. Result: ask the worker to reply in the Result format below, save the reply
   as a file, then run `import-result`. This also writes the Glow return pack
   (folder set by `--glow-out`). Paste that pack to Glow yourself.
5. `glow-pack` is only for regenerating the pack later or building one without
   a new result. Use `--no-glow-pack` on `import-result` to skip it.

Result format (exact sections): Changes, Verification evidence, Blockers,
Next action, Decisions.
```

*Replace "CLI reference":*
```markdown
./cb init "Name" [--repo path]
./cb import-plan "Name" plan.md [--task-id ID] [--version V] [--repo path] [--replace-decisions]
./cb export "Name" "Claude|Grok Bot|…"
./cb route "Name" [--task-id ID] [--role coding|explore] [--override claude|grok] [--json]
./cb packet "Name" claude|grok [--task-id ID] [--reason unavailable|failed]
    [--error-class C] [--error-message M] [--instructions TEXT] [--out DIR]
./cb import-result "Name" result.md|result.json [--author A] [--task-id ID]
    [--based-on-version V] [--glow-out DIR] [--no-glow-pack]
./cb glow-pack "Name" [--result result.md|result.json] [--task-id ID]
    [--based-on-version V] [--out DIR]
./cb status ["Name"]
./cb validate-plan plan.md
```
(`export`, `status`, `validate-plan` lines are unchanged pending their help output.)

*Reword the CB-005 last bullet:*
```markdown
- CB-005 is not closed: it stays FAIL until Glow re-verifies the fidelity and scrub fixes.
```

## Verification evidence
- Compared README text against the supplied CLI help dump only. No commands were run, no demos executed, and no repo was edited.
- Confirmed the dump's version string is `Context Bridge 1.1.2`, matching the README.
- Confirmed all nine subcommands in the README exist in the CLI.
- Confirmed every flag listed in the README exists for `init`, `import-plan`, `route`, `packet`, `import-result`, and `glow-pack`.
- Found 11 CLI flags absent from the README: 2 on `import-plan`, 1 on `route`, 4 on `packet` (the 5th, `--reason`, is listed), 2 on `import-result`, 3 on `glow-pack`. That is 12 counting `--task-id` on `packet` and `glow-pack` separately; the table above lists them all.

## Blockers
- Help output for `export`, `status`, and `validate-plan` was not provided. Their README lines were not checked and no help was invented for them.
- Unverifiable from the dump: the `--reason` default, the meaning of exit code 2 from `route`, the `python3 -m context_bridge` entry point, and whether the demo scripts and test modules exist.
- Pilot status: **NOT COMPLETED.**

## Next action
Glow supplies `cb export -h`, `cb status -h`, and `cb validate-plan -h`, plus confirmation of the `--reason` default and the `route` exit-code behavior. Claude then finalizes the README wording as a follow-up result under CB-006.

## Decisions
- Scope held to proposed wording only, with no repo edits.
- Demos were not run and no flowchart was drawn.
- Proposed text covers only flags confirmed by the help dump. Unconfirmed items were left unchanged or listed under Blockers.
- CB-006 remains open, based on version 1.1.2.
