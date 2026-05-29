from __future__ import annotations

import json
import os
import signal
import sys
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PROC_ROOT = Path("/proc")
MCP_KINDS = (
    "serena",
    "youtrack/mcp-remote",
    "telegram",
    "context7",
    "playwright",
    "slack",
)


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    ppid: int
    name: str
    argv: list[str]
    cmdline: str
    start_ts: float
    rss_kb: int = 0
    pss_kb: int = 0


@dataclass(frozen=True)
class Launcher:
    pid: int
    kind: str
    start_ts: float
    descendant_count: int
    rss_kb: int
    pss_kb: int


@dataclass(frozen=True)
class CleanupResult:
    root_pid: int
    since_ts: float
    killset: set[int]
    launchers: list[Launcher]


def state_dir() -> Path:
    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    if xdg_state_home:
        return Path(xdg_state_home) / "codex-mcp-clean"
    return Path.home() / ".local" / "state" / "codex-mcp-clean"


def ensure_linux_proc(platform: str | None = None, proc_root_exists: bool | None = None) -> None:
    platform = sys.platform if platform is None else platform
    proc_root_exists = PROC_ROOT.exists() if proc_root_exists is None else proc_root_exists
    if not platform.startswith("linux"):
        raise SystemExit("codex-mcp-clean is Linux-only because it reads process data from /proc.")
    if not proc_root_exists:
        raise SystemExit("codex-mcp-clean requires a mounted /proc filesystem.")


def read_processes(proc_root: Path = PROC_ROOT) -> dict[int, ProcessInfo]:
    boot_ts = time.time() - float((proc_root / "uptime").read_text().split()[0])
    clk_tck = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
    processes: dict[int, ProcessInfo] = {}

    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            status_lines = (entry / "status").read_text(errors="replace").splitlines()
            stat_text = (entry / "stat").read_text(errors="replace")
            raw_cmdline = (entry / "cmdline").read_bytes()
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue

        name = ""
        ppid = 0
        rss_kb = 0
        for line in status_lines:
            if line.startswith("Name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("PPid:"):
                ppid = int(line.split(":", 1)[1].strip() or 0)
            elif line.startswith("VmRSS:"):
                parts = line.split()
                rss_kb = int(parts[1]) if len(parts) > 1 else 0

        pss_kb = read_pss_kb(entry, rss_kb)
        start_ts = read_start_ts(stat_text, boot_ts, clk_tck)
        argv = [item.decode("utf-8", "replace") for item in raw_cmdline.split(b"\0")[:-1]]
        processes[pid] = ProcessInfo(
            pid=pid,
            ppid=ppid,
            name=name,
            argv=argv,
            cmdline=" ".join(argv),
            start_ts=start_ts,
            rss_kb=rss_kb,
            pss_kb=pss_kb,
        )

    return processes


def read_pss_kb(process_dir: Path, fallback_rss_kb: int) -> int:
    try:
        for line in (process_dir / "smaps_rollup").read_text(errors="replace").splitlines():
            if line.startswith("Pss:"):
                parts = line.split()
                return int(parts[1]) if len(parts) > 1 else fallback_rss_kb
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        pass
    return fallback_rss_kb


def read_start_ts(stat_text: str, boot_ts: float, clk_tck: int) -> float:
    try:
        # Field 22 (starttime) appears after the final ")" because comm may
        # contain spaces or parentheses.
        rest = stat_text.rsplit(")", 1)[1].strip().split()
        return boot_ts + int(rest[19]) / clk_tck
    except (IndexError, ValueError):
        return 0.0


def child_map(processes: dict[int, ProcessInfo]) -> dict[int, list[int]]:
    children: dict[int, list[int]] = defaultdict(list)
    for pid, process in processes.items():
        children[process.ppid].append(pid)
    return children


def descendants_of(processes: dict[int, ProcessInfo], root_pid: int) -> list[int]:
    children = child_map(processes)
    descendants: list[int] = []
    queue: deque[int] = deque(children.get(root_pid, []))
    while queue:
        pid = queue.popleft()
        if pid not in processes:
            continue
        descendants.append(pid)
        queue.extend(children.get(pid, []))
    return descendants


def is_codex_appserver(process: ProcessInfo) -> bool:
    if not process.argv:
        return False
    return os.path.basename(process.argv[0]) == "codex" and "app-server" in process.argv


def mcp_launcher_kind(process: ProcessInfo) -> str | None:
    if not process.argv:
        return None

    base = os.path.basename(process.argv[0])
    joined = " ".join(process.argv).lower()
    name = process.name

    if name.startswith("npm exec mcp-re") or (base in {"npm", "npx"} and "mcp-remote" in joined):
        return "youtrack/mcp-remote"
    if name.startswith("mcp-telegram") or base in {"mcp-telegram", "mcp-telegram-codex"}:
        return "telegram"
    if base in {"uv", "uvx"} and "serena" in joined:
        return "serena"
    if name.startswith("npm exec @upsta") or (base in {"npm", "npx"} and "context7" in joined):
        return "context7"
    if name.startswith("npm exec @playw") or (base in {"npm", "npx"} and "@playwright/mcp" in joined):
        return "playwright"
    if name.startswith("npm exec @jtalk") or (base in {"npm", "npx"} and "slack-mcp" in joined):
        return "slack"
    return None


def compute_cleanup_set(
    processes: dict[int, ProcessInfo],
    root_pid: int,
    since_ts: float,
) -> tuple[set[int], list[Launcher]]:
    children = child_map(processes)
    killset: set[int] = set()
    launchers: list[Launcher] = []

    for pid in sorted(children.get(root_pid, []), key=lambda item: processes[item].start_ts):
        process = processes.get(pid)
        if process is None or process.start_ts < since_ts:
            continue
        kind = mcp_launcher_kind(process)
        if kind is None:
            continue

        subtree = {pid, *descendants_of(processes, pid)}
        killset.update(subtree)
        launchers.append(
            Launcher(
                pid=pid,
                kind=kind,
                start_ts=process.start_ts,
                descendant_count=len(subtree) - 1,
                rss_kb=sum(processes[item].rss_kb for item in subtree if item in processes),
                pss_kb=sum(processes[item].pss_kb for item in subtree if item in processes),
            )
        )

    killset.discard(os.getpid())
    return killset, launchers


def appserver_summaries(processes: dict[int, ProcessInfo]) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    children = child_map(processes)

    for pid, process in sorted(processes.items()):
        if not is_codex_appserver(process):
            continue

        subtree = {pid, *descendants_of(processes, pid)}
        direct_launchers = [
            child
            for child in children.get(pid, [])
            if child in processes and mcp_launcher_kind(processes[child]) is not None
        ]
        launcher_counts: dict[str, int] = defaultdict(int)
        for child in direct_launchers:
            kind = mcp_launcher_kind(processes[child])
            if kind is not None:
                launcher_counts[kind] += 1

        summaries.append(
            {
                "pid": pid,
                "ppid": process.ppid,
                "start_ts": round(process.start_ts, 3),
                "start_local": format_ts(process.start_ts),
                "descendants": len(subtree) - 1,
                "rss_mib": round(sum(processes[item].rss_kb for item in subtree if item in processes) / 1024, 1),
                "pss_mib": round(sum(processes[item].pss_kb for item in subtree if item in processes) / 1024, 1),
                "mcp_launcher_roots": len(direct_launchers),
                "mcp_launcher_counts": dict(sorted(launcher_counts.items())),
            }
        )

    return summaries


def snapshot_path(root_pid: int) -> Path:
    return state_dir() / f"snapshot-{root_pid}.json"


def save_snapshot(root_pid: int, now: float | None = None) -> dict[str, object]:
    now = time.time() if now is None else now
    state_dir().mkdir(parents=True, exist_ok=True)
    payload = {
        "root_pid": root_pid,
        "since_ts": now,
        "since_local": format_ts(now),
        "path": str(snapshot_path(root_pid)),
    }
    snapshot_path(root_pid).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return payload


def load_snapshot(root_pid: int) -> dict[str, object]:
    path = snapshot_path(root_pid)
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise SystemExit(f"No snapshot found for root pid {root_pid}. Run: codex-mcp-clean snapshot --root-pid {root_pid}") from exc


def parse_since(value: str | None, root_pid: int | None = None) -> float:
    if value is None:
        if root_pid is None:
            raise SystemExit("--since or --root-pid is required")
        snapshot = load_snapshot(root_pid)
        return float(snapshot["since_ts"])

    try:
        return float(value)
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return time.mktime(time.strptime(value, fmt))
        except ValueError:
            continue
    raise SystemExit(f"Could not parse --since value: {value!r}")


def cleanup_result(processes: dict[int, ProcessInfo], root_pid: int, since_ts: float) -> CleanupResult:
    killset, launchers = compute_cleanup_set(processes, root_pid, since_ts)
    return CleanupResult(root_pid=root_pid, since_ts=since_ts, killset=killset, launchers=launchers)


def terminate_processes(killset: set[int], grace_seconds: float = 2.0) -> dict[str, object]:
    current = os.getpid()
    killset = set(killset)
    killset.discard(current)

    term_errors: list[str] = []
    for pid in sorted(killset, reverse=True):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError as exc:
            term_errors.append(f"TERM {pid}: {exc}")

    time.sleep(grace_seconds)

    remaining = [pid for pid in sorted(killset) if (PROC_ROOT / str(pid)).exists()]
    kill_errors: list[str] = []
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError as exc:
            kill_errors.append(f"KILL {pid}: {exc}")

    return {
        "term_sent": len(killset),
        "sigkill_remaining": len(remaining),
        "term_errors": term_errors,
        "kill_errors": kill_errors,
    }


def launcher_payload(launchers: Iterable[Launcher]) -> list[dict[str, object]]:
    return [
        {
            "pid": item.pid,
            "kind": item.kind,
            "start_ts": round(item.start_ts, 3),
            "start_local": format_ts(item.start_ts),
            "descendants": item.descendant_count,
            "rss_mib": round(item.rss_kb / 1024, 1),
            "pss_mib": round(item.pss_kb / 1024, 1),
        }
        for item in launchers
    ]


def result_payload(result: CleanupResult, dry_run: bool | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "root_pid": result.root_pid,
        "since_ts": round(result.since_ts, 3),
        "since_local": format_ts(result.since_ts),
        "processes_total": len(result.killset),
        "launcher_roots": len(result.launchers),
        "launchers": launcher_payload(result.launchers),
    }
    if dry_run is not None:
        payload["dry_run"] = dry_run
    return payload


def format_ts(ts: float) -> str:
    return time.strftime("%F %T %z", time.localtime(ts))
