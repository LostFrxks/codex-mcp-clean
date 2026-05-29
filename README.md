# codex-mcp-clean

Linux-only diagnostic/workaround CLI for reporting and cleaning leaked MCP
process stacks under a specific Codex `app-server` PID.

This is not an official OpenAI tool. It exists to make MCP process growth easy
to measure, reproduce, and clean up after controlled Codex subagent batches.

## Why

Codex subagents can start their own stdio MCP process stacks. If those stacks
are not cleaned up after the subagents finish, process count and memory usage
can grow linearly under the long-lived `codex app-server`.

`codex-mcp-clean` helps with two things:

- report the MCP footprint under each live Codex app-server;
- clean only MCP launcher subtrees that were created after a saved snapshot.

## Supported Platform

Linux only.

The tool reads process data from `/proc`, including `/proc/<pid>/cmdline`,
`/proc/<pid>/status`, and `/proc/<pid>/smaps_rollup`. Windows and macOS are not
supported.

## Install

Recommended Linux install from a local checkout:

```bash
./scripts/install.sh
```

The installer creates an isolated virtualenv under
`~/.local/share/codex-mcp-clean/venv` and writes the executable wrapper to
`~/.local/bin/codex-mcp-clean`.

If `python3-venv` is not installed, the installer falls back to a source
wrapper that points at the checkout directory. That fallback works immediately,
but you should keep the checkout in place.

Uninstall:

```bash
./scripts/uninstall.sh
```

Alternative install from a local checkout:

```bash
python3 -m pip install --user .
```

On Linux distributions that enable PEP 668, direct `pip --user` installation
may be blocked. Use the installer above or `pipx`:

```bash
pipx install .
```

Check that the command is available:

```bash
codex-mcp-clean --version
```

## Workflow

List live Codex app-server processes and their MCP footprint:

```bash
codex-mcp-clean list
```

Save a cutoff timestamp before a controlled subagent batch:

```bash
codex-mcp-clean snapshot --root-pid <PID>
```

Run the subagents, wait for them to complete, and close them.

Report MCP launcher subtrees created after the snapshot:

```bash
codex-mcp-clean report --root-pid <PID>
```

Dry-run cleanup:

```bash
codex-mcp-clean cleanup --root-pid <PID>
```

Actually terminate the matching MCP subtrees:

```bash
codex-mcp-clean cleanup --root-pid <PID> --kill
```

Machine-readable output is available for reports and bug reports:

```bash
codex-mcp-clean list --json
codex-mcp-clean report --root-pid <PID> --json
codex-mcp-clean cleanup --root-pid <PID> --json
```

## Safety Model

`cleanup` is a dry-run unless `--kill` is passed.

The kill set is intentionally narrow. The tool targets only processes that:

- are direct MCP launcher children of the selected Codex app-server PID;
- started after the saved snapshot or explicit `--since` timestamp;
- match known MCP launchers such as Serena, Telegram, YouTrack/mcp-remote,
  Context7, Playwright, or Slack.

It does not kill MCP processes under other Codex app-server PIDs.

It cannot distinguish two overlapping subagent batches inside the same
`app-server` PID. Take the snapshot immediately before the controlled batch and
run cleanup only after that batch is closed.

## Development

Run tests:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

Run the CLI without installing:

```bash
python3 -m codex_mcp_clean.cli list
```

## GitHub Issue Wording

Useful one-liner for upstream bug reports:

> I used `codex-mcp-clean`, a Linux-only diagnostic/workaround tool, to snapshot
> a Codex app-server PID and clean MCP launcher subtrees created after the
> snapshot. Returning memory/process count to baseline after killing those
> subtrees suggests stale MCP child trees are the source of the growth.

A longer upstream issue template is available in
[`docs/upstream-issue-template.md`](docs/upstream-issue-template.md).
