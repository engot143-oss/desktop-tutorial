# Brief for Grok Bot — CB-004 fix (from Glow FAIL on CB-003)

| Field | Value |
|-------|--------|
| Project | Context Bridge |
| Task ID | CB-004 |
| Based on | CB-003 / v1.1.0 FAIL |
| Version target | 1.1.1 |

## Must fix
**1. Exact four-section contract (FAIL)**
- Import must reject reordered, altered, or duplicate Glow headings (Goal / Constraints / Open questions / Who gets what next).
- Do not strip surrounding whitespace or join continuation lines in a way that breaks byte-exact section body fidelity on round-trip.

**2. Credential redaction (FAIL)**
- Synthetic key was redacted from Goal body and JSON but leaked via project metadata and "Blocked until".
- Scrub free-text secrets in all export surfaces: plan bodies, metadata fields, Blocked until, MD and JSON.

## Required
Regression tests for both failures. Re-run unittest suite + `demo_round_trip.sh` + `demo_v11_ops.sh`. Report path for Glow re-verify.

## Constraints
Local-only; no credentials in handoffs; no live connections / deploy / repo changes unless Enrique asks.
