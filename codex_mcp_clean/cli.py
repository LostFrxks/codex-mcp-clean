from __future__ import annotations

import argparse
import json

from . import __version__
from . import core


def print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def print_report(payload: dict[str, object]) -> None:
    print(
        f"root_pid={payload['root_pid']} since={payload['since_local']} "
        f"launcher_roots={payload['launcher_roots']} processes_total={payload['processes_total']}"
    )
    for item in payload["launchers"]:
        print(
            f"  {item['pid']} {item['kind']:20s} start={item['start_local']} "
            f"desc={item['descendants']} rss={item['rss_mib']}MiB pss={item['pss_mib']}MiB"
        )


def cmd_list(args: argparse.Namespace) -> int:
    payload = core.appserver_summaries(core.read_processes())
    if args.json:
        print_json(payload)
        return 0

    if not payload:
        print("No codex app-server processes found.")
        return 0

    for item in payload:
        print(
            f"appserver={item['pid']} descendants={item['descendants']} "
            f"rss={item['rss_mib']}MiB pss={item['pss_mib']}MiB "
            f"mcp_roots={item['mcp_launcher_roots']} start={item['start_local']}"
        )
        counts = item["mcp_launcher_counts"]
        if counts:
            print("  " + " ".join(f"{key}={value}" for key, value in counts.items()))
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    processes = core.read_processes()
    root = processes.get(args.root_pid)
    if root is None or not core.is_codex_appserver(root):
        raise SystemExit(f"PID {args.root_pid} is not a live codex app-server")

    payload = core.save_snapshot(args.root_pid)
    if args.json:
        print_json(payload)
    else:
        print(f"snapshot saved: {payload['path']}")
        print(f"root_pid={payload['root_pid']} since_ts={payload['since_ts']:.3f} since_local={payload['since_local']}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    since_ts = core.parse_since(args.since, args.root_pid)
    result = core.cleanup_result(core.read_processes(), args.root_pid, since_ts)
    payload = core.result_payload(result)
    if args.json:
        print_json(payload)
    else:
        print_report(payload)
    return 0


def cmd_cleanup(args: argparse.Namespace) -> int:
    since_ts = core.parse_since(args.since, args.root_pid)
    result = core.cleanup_result(core.read_processes(), args.root_pid, since_ts)
    payload = core.result_payload(result, dry_run=not args.kill)

    if not args.kill:
        if args.json:
            print_json(payload)
        else:
            print_report(payload)
            print("dry-run: no processes killed. Re-run with --kill to terminate these MCP subtrees.")
        return 0

    payload.update(core.terminate_processes(result.killset, grace_seconds=args.grace_seconds))
    if args.json:
        print_json(payload)
    else:
        print_report(payload)
        print(
            f"killed: TERM sent to {payload['term_sent']} processes; "
            f"SIGKILL fallback attempted for {payload['sigkill_remaining']}"
        )
        for error in payload["term_errors"] + payload["kill_errors"]:
            print(f"  error: {error}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-mcp-clean",
        description="Report and clean leaked MCP process bundles under a specific Codex app-server PID.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List live codex app-server PIDs and MCP footprint.")
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(func=cmd_list)

    snapshot_parser = subparsers.add_parser("snapshot", help="Save a cleanup cutoff timestamp for one app-server PID.")
    snapshot_parser.add_argument("--root-pid", type=int, required=True)
    snapshot_parser.add_argument("--json", action="store_true")
    snapshot_parser.set_defaults(func=cmd_snapshot)

    report_parser = subparsers.add_parser("report", help="Show MCP launcher subtrees created after a snapshot/cutoff.")
    report_parser.add_argument("--root-pid", type=int, required=True)
    report_parser.add_argument("--since", help="Epoch timestamp or local 'YYYY-MM-DD HH:MM:SS'. Defaults to saved snapshot.")
    report_parser.add_argument("--json", action="store_true")
    report_parser.set_defaults(func=cmd_report)

    cleanup_parser = subparsers.add_parser("cleanup", help="Dry-run or kill MCP launcher subtrees after a snapshot/cutoff.")
    cleanup_parser.add_argument("--root-pid", type=int, required=True)
    cleanup_parser.add_argument("--since", help="Epoch timestamp or local 'YYYY-MM-DD HH:MM:SS'. Defaults to saved snapshot.")
    cleanup_parser.add_argument("--kill", action="store_true", help="Actually terminate matching MCP subtrees. Default is dry-run.")
    cleanup_parser.add_argument("--grace-seconds", type=float, default=2.0)
    cleanup_parser.add_argument("--json", action="store_true")
    cleanup_parser.set_defaults(func=cmd_cleanup)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    core.ensure_linux_proc()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
