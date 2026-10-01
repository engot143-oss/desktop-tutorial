# Goal

Resolve the independently reproduced failures and provide a complete package for Glow’s re-verification.

# Constraints

* Keep the hierarchy Eric → Glow → Grok Bot → Claude / Grok.
* Keep execution manual-first and local-only. No live worker connections or deployment.
* Work in a local branch. Do not push or merge without Eric’s instruction.
* Use synthetic secrets only.
* Preserve non-secret section bodies byte-for-byte. Credential redaction is the only permitted body transformation.
* Completion claims and passing supplied tests do not establish Glow’s PASS.

# Open questions

* None for these fixes. If preserving the existing contract requires a design change, report it before changing the contract.

# Who gets what next

* Grok Bot: Implement the fixes and regressions below.
* Claude / Grok: Support implementation or review through manual handoffs as needed.
* Glow: Independently inspect and rerun verification.
* Eric: Review the returned package and any proposed push or merge.
