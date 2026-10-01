# Prompt for Glow — CB-005 / Context Bridge

Paste this into Glow:

---

Context Bridge lives on GitHub main:
https://github.com/engot143-oss/desktop-tutorial/tree/main/context-bridge

CB-005 brief for Grok Bot (v1.1.2 fixes) is in-repo:
https://github.com/engot143-oss/desktop-tutorial/blob/main/context-bridge/handoffs/CB-005-grok-bot-fix.md

Also:
- Plan: context-bridge/handoffs/CB-005-glow-plan.md
- Export: context-bridge/handoffs/exports/CB-005-grok-bot-v1.1.2.md

Current status: v1.1.1 on main is FAIL pending CB-005 (v1.1.2). Grok Bot is implementing locally — no push/merge of the fix without Eric’s say-so.

When Grok Bot returns the v1.1.2 package: independently re-verify the four required fixes (multi-cycle whitespace, CRLF/nested headings, scrub leaks, literal titles), then PASS or FAIL with evidence. Do not treat supplied tests alone as PASS.

---
