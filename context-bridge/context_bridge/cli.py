"""Context Bridge CLI — local handoff tool (authoritative for v1.1 ops)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from . import store
from .adapters.manual import create_manual_packet
from .export import export_handoff
from .glow_pack import write_glow_return_pack
from .live_send import send_hop
from .plan_import import PlanImportError, import_plan_file, parse_glow_plan_markdown
from .result_import import ResultImportError, apply_result, load_result
from .route import route_task


def cmd_init(args: argparse.Namespace) -> int:
    ctx = store.ensure_project(args.project, repo_path=args.repo)
    print(f"Initialized project '{ctx.project}' at {store.project_dir(ctx.project)}")
    print(f"  context: {store.project_dir(ctx.project) / 'context.json'}")
    return 0


def cmd_import_plan(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 1
    try:
        ctx = store.load_context(args.project)
    except FileNotFoundError:
        ctx = store.ensure_project(args.project, repo_path=args.repo)
    try:
        ctx = import_plan_file(
            path,
            ctx,
            task_id=args.task_id,
            version=args.version,
            merge_decisions=not args.replace_decisions,
        )
    except PlanImportError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    store.save_context(ctx)
    print(f"Imported Glow plan into '{ctx.project}'")
    print(f"  task_id={ctx.current_task_id} version={ctx.current_version}")
    print(f"  decisions={len(ctx.decisions)} assumptions={len(ctx.assumptions)}")
    if ctx.glow_plan:
        print(f"  goal: {ctx.glow_plan.goal[:80]}...")
        print(
            "  sections OK: Goal / Constraints / Open questions / Who gets what next"
        )
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    ctx = store.load_context(args.project)
    out = Path(args.out) if args.out else None
    try:
        md_path, json_path, h = export_handoff(
            ctx, args.recipient, out_dir=out, source=args.source or "Context Bridge"
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"Exported handoff for {h.recipient}")
    print(f"  markdown: {md_path}")
    print(f"  json:     {json_path}")
    print(f"  task={h.handoff_id} version={h.version} decisions={len(h.decisions)}")
    return 0


def cmd_import_result(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 1
    ctx = store.load_context(args.project)
    try:
        result = load_result(path)
    except ResultImportError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if args.author:
        result.author = args.author
    if args.task_id:
        result.handoff_id = args.task_id
    if args.based_on_version:
        result.based_on_version = args.based_on_version
    if not result.project:
        result.project = ctx.project
    if not result.handoff_id and not args.task_id:
        result.handoff_id = ctx.current_task_id or ""

    ctx, flags = apply_result(ctx, result)
    store.save_context(ctx)

    print(f"Imported result from {result.author or path.name}")
    print(
        f"  task_id={result.handoff_id or '(none)'} "
        f"based_on={result.based_on_version or '(none)'}"
    )
    print(f"  changes={len(result.changes)} evidence={len(result.verification_evidence)}")
    print(f"  blockers={len(result.blockers)}")
    print(f"  new_decisions={len(result.new_decisions)}")
    na_preview = result.next_action.replace("\n", " | ")
    print(f"  next_action: {na_preview[:160]}")
    print(f"  decisions now: {len(ctx.decisions)} (earlier decisions preserved)")
    if flags:
        print(f"  FLAGS ({len(flags)}):")
        for f in flags:
            print(f"    [{f['type']}] {f['message']}")
    else:
        print("  FLAGS: none")

    # Slice B: always emit Glow return pack after import-result
    if not getattr(args, "no_glow_pack", False):
        out = Path(args.glow_out) if getattr(args, "glow_out", None) else None
        md_path, json_path, pack = write_glow_return_pack(ctx, result, out_dir=out)
        print("Glow return pack:")
        print(f"  markdown: {md_path}")
        print(f"  json:     {json_path}")
        print(
            f"  open_flags={len(pack.get('open_flags') or [])} "
            f"summary={pack.get('flag_summary')}"
        )
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    """Slice A: print chosen worker + reason (or clarify)."""
    ctx = store.load_context(args.project)
    decision = route_task(
        ctx,
        override=args.override,
        role=args.role,
        task_id=args.task_id,
    )
    print(f"route status: {decision.status}")
    if decision.worker:
        print(f"worker: {decision.worker}")
    else:
        print("worker: (none — clarification required)")
    print(f"reason: {decision.reason}")
    if decision.candidates:
        print("candidates:")
        for w, action in decision.candidates.items():
            print(f"  - {w}: {action[:120]}")
    if args.json:
        print(json.dumps(decision.to_dict(), indent=2))
    return 0 if decision.status == "ok" else 2


def cmd_packet(args: argparse.Namespace) -> int:
    """Slice C: write manual awaiting_execution packet for claude|grok."""
    ctx = store.load_context(args.project)
    if args.task_id:
        ctx.current_task_id = args.task_id
    out = Path(args.out) if args.out else None
    try:
        result = create_manual_packet(
            ctx,
            args.worker,
            reason=args.reason,
            error_class=args.error_class,
            error_message=args.error_message,
            instructions=args.instructions,
            out_dir=out,
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    store.save_context(ctx)
    print(f"Manual packet for {result.worker}")
    print(f"  status: {result.status.value}")
    print(f"  underlying connection: {result.details.get('underlying')}")
    print(f"  error_class: {result.error_class}")
    print(f"  packet: {result.packet_path}")
    print(f"  message: {result.message}")
    return 0


def cmd_glow_pack(args: argparse.Namespace) -> int:
    """Slice B: emit Glow return pack from current context (+ optional result file)."""
    ctx = store.load_context(args.project)
    result = None
    if args.result:
        path = Path(args.result)
        if not path.exists():
            print(f"ERROR: file not found: {path}", file=sys.stderr)
            return 1
        result = load_result(path)
        if args.task_id:
            result.handoff_id = args.task_id
        if args.based_on_version:
            result.based_on_version = args.based_on_version
    out = Path(args.out) if args.out else None
    md_path, json_path, pack = write_glow_return_pack(ctx, result, out_dir=out)
    print("Glow return pack:")
    print(f"  markdown: {md_path}")
    print(f"  json:     {json_path}")
    print(f"  task_id={pack.get('task_id')} based_on={pack.get('based_on_version')}")
    print(f"  open_flags={len(pack.get('open_flags') or [])}")
    for f in pack.get("open_flags") or []:
        print(f"    [{f.get('type')}] {f.get('message')}")
    return 0


def cmd_send(args: argparse.Namespace) -> int:
    """One live hop. Falls back to a manual packet; does not crash or drop context."""
    try:
        ctx = store.load_context(args.project)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if args.task_id:
        ctx.current_task_id = args.task_id
    try:
        outcome = send_hop(
            ctx,
            args.worker,
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
            dry_run=args.dry_run,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            out_dir=Path(args.out) if args.out else None,
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if outcome.dry_run:
        print(outcome.preview, end="" if outcome.preview.endswith("\n") else "\n")
        return outcome.exit_code

    if outcome.fell_back and outcome.result is not None:
        underlying = (outcome.result.details or {}).get("underlying")
        print("FALLBACK: manual packet (live hop did not complete)")
        print(f"  worker: {outcome.result.worker}")
        print(f"  provider: {outcome.provider}")
        print(f"  model: {outcome.model}")
        print(f"  status: {outcome.result.status.value}")
        print(f"  connection: {underlying}")
        print(f"  error_class: {outcome.result.error_class}")
        print(f"  error_message: {outcome.result.error_message}")
        print(f"  packet: {outcome.result.packet_path}")
        print(f"  message: {outcome.result.message}")
        print("Context saved. Paste the packet to the worker, then cb import-result.")
        return outcome.exit_code

    if outcome.result is not None and outcome.result.status.value == "success":
        print("Live hop complete")
        print(f"  worker: {outcome.result.worker}")
        print(f"  provider: {outcome.provider}")
        print(f"  model: {outcome.model}")
        print(f"  status: {outcome.result.status.value}")
        print(f"  result: {outcome.result_path}")
        if outcome.glow_md:
            print(f"  glow markdown: {outcome.glow_md}")
        if outcome.glow_json:
            print(f"  glow json: {outcome.glow_json}")
        if outcome.note:
            print(f"  note: {outcome.note}")
        print(f"  message: {outcome.result.message}")
        return outcome.exit_code

    print("ERROR: send finished without a result or a manual packet.", file=sys.stderr)
    return 1


def cmd_status(args: argparse.Namespace) -> int:
    if args.project:
        ctx = store.load_context(args.project)
        print(json.dumps(ctx.to_dict(), indent=2))
        return 0
    projects = store.list_projects()
    if not projects:
        print("No projects. Run: cb init <name>")
        return 0
    for p in projects:
        ctx = store.load_context(p)
        flags = len(ctx.flags)
        print(
            f"- {ctx.project}  task={ctx.current_task_id}  "
            f"v={ctx.current_version}  decisions={len(ctx.decisions)}  flags={flags}"
        )
    return 0


def cmd_validate_plan(args: argparse.Namespace) -> int:
    path = Path(args.file)
    text = path.read_text(encoding="utf-8")
    try:
        plan, meta, decisions, assumptions, assigned = parse_glow_plan_markdown(text)
    except PlanImportError as e:
        print(f"INVALID: {e}", file=sys.stderr)
        return 1
    print("VALID Glow plan")
    print(f"  goal length: {len(plan.goal)}")
    print(f"  constraints: {len(plan.constraints)}")
    print(f"  open_questions: {len(plan.open_questions)}")
    print(f"  who_gets_what_next: {list(plan.who_gets_what_next.keys())}")
    print(f"  meta: {meta}")
    print(
        f"  decisions: {len(decisions)} assumptions: {len(assumptions)} "
        f"assigned: {len(assigned)}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cb",
        description=(
            "Context Bridge v1.2 — local engineering handoff tool. "
            "CLI is authoritative. `cb packet` is manual paste. "
            "`cb send` tries one live hop and falls back to a manual packet."
        ),
    )
    p.add_argument("--version", action="version", version=f"Context Bridge {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="Initialize saved project context")
    s.add_argument("project", help="Project name")
    s.add_argument("--repo", default=None, help="Repo / path (optional)")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("import-plan", help="Import Glow four-section Markdown plan")
    s.add_argument("project", help="Project name")
    s.add_argument("file", help="Path to Markdown plan")
    s.add_argument("--task-id", default=None)
    s.add_argument("--version", default=None)
    s.add_argument("--repo", default=None)
    s.add_argument(
        "--replace-decisions",
        action="store_true",
        help="Replace decisions instead of merging (default: merge/preserve)",
    )
    s.set_defaults(func=cmd_import_plan)

    s = sub.add_parser("export", help="Export recipient-specific handoff (MD + JSON)")
    s.add_argument("project", help="Project name")
    s.add_argument("recipient", help="Recipient name (e.g. Claude, Grok Bot)")
    s.add_argument("--out", default=None, help="Output directory")
    s.add_argument("--source", default=None)
    s.set_defaults(func=cmd_export)

    s = sub.add_parser(
        "import-result",
        help="Import result; emits Glow return pack (Slice B)",
    )
    s.add_argument("project", help="Project name")
    s.add_argument("file", help="Path to result Markdown or JSON")
    s.add_argument("--author", default=None)
    s.add_argument("--task-id", default=None)
    s.add_argument("--based-on-version", default=None)
    s.add_argument("--glow-out", default=None, help="Directory for Glow return pack")
    s.add_argument(
        "--no-glow-pack",
        action="store_true",
        help="Skip automatic Glow return pack (not recommended)",
    )
    s.set_defaults(func=cmd_import_result)

    s = sub.add_parser(
        "route",
        help="Slice A: choose worker claude|grok from Who gets what next",
    )
    s.add_argument("project", help="Project name")
    s.add_argument("--task-id", default=None)
    s.add_argument(
        "--override",
        choices=["claude", "grok"],
        default=None,
        help="Glow override — always wins",
    )
    s.add_argument(
        "--role",
        choices=["coding", "explore"],
        default=None,
        help="Default role hint when both workers are assigned",
    )
    s.add_argument("--json", action="store_true", help="Also print JSON decision")
    s.set_defaults(func=cmd_route)

    s = sub.add_parser(
        "packet",
        help="Slice C: write manual awaiting_execution packet (no live call)",
    )
    s.add_argument("project", help="Project name")
    s.add_argument("worker", choices=["claude", "grok"])
    s.add_argument("--task-id", default=None)
    s.add_argument(
        "--reason",
        choices=["unavailable", "failed"],
        default="unavailable",
        help="unavailable=no live link; failed=attempted live call failed",
    )
    s.add_argument("--error-class", default=None)
    s.add_argument("--error-message", default=None)
    s.add_argument("--instructions", default=None)
    s.add_argument("--out", default=None, help="Packet output directory")
    s.set_defaults(func=cmd_packet)

    s = sub.add_parser(
        "send",
        help="One live hop; manual packet if no key, no endpoint, or the call fails",
    )
    s.add_argument("project", help="Project name")
    s.add_argument(
        "worker",
        choices=["claude", "grok", "glow", "chatgpt"],
        help="Worker role (provider defaults: claude=anthropic, grok=xai, glow/chatgpt=openai)",
    )
    s.add_argument("--task-id", default=None)
    s.add_argument(
        "--provider",
        default=None,
        help="anthropic, xai, openai, openai-compatible (alias: ollama)",
    )
    s.add_argument("--model", default=None, help="Override the provider model")
    s.add_argument(
        "--base-url",
        default=None,
        help="Override the provider base URL (OpenAI-compatible default: http://localhost:11434/v1)",
    )
    s.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the exact request that would be sent; do not call or write",
    )
    s.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Per-call output cap (default 1024, hard cap 4096)",
    )
    s.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Per-call timeout in seconds (default 60, hard cap 120)",
    )
    s.add_argument("--out", default=None, help="Directory for a fallback manual packet")
    s.set_defaults(func=cmd_send)

    s = sub.add_parser(
        "glow-pack",
        help="Slice B: write Glow return pack from context (+ optional result)",
    )
    s.add_argument("project", help="Project name")
    s.add_argument("--result", default=None, help="Optional result MD/JSON to include")
    s.add_argument("--task-id", default=None)
    s.add_argument("--based-on-version", default=None)
    s.add_argument("--out", default=None)
    s.set_defaults(func=cmd_glow_pack)

    s = sub.add_parser("status", help="Show project context or list projects")
    s.add_argument("project", nargs="?", default=None)
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("validate-plan", help="Validate Glow four-section Markdown")
    s.add_argument("file", help="Path to Markdown plan")
    s.set_defaults(func=cmd_validate_plan)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
