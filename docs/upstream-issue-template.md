# Upstream Issue Template

Use this as supporting text when reporting Codex MCP process growth upstream.

```md
## Summary

Codex app-server appears to start a full stdio MCP process stack for each
subagent/session. After subagents finish and are closed, those MCP child process
trees do not reliably return to the baseline, causing linear process and memory
growth under the long-lived `codex app-server`.

## Environment

- Codex CLI: `codex-cli 0.128.0`
- OS: Ubuntu 24.04.4 LTS, Linux 6.17.0-29-generic, x86_64
- Machine: 16 GB RAM, 16 GB swap, 8 CPU cores
- Surface: Codex app-server / IDE integration
- Reduced MCP set:
  - Serena
  - Telegram
  - YouTrack via `mcp-remote`

## Reproduction Pattern

1. Start Codex app-server with stdio MCP servers enabled.
2. Take a baseline process/memory snapshot of the `codex app-server` child tree.
3. Spawn 10 subagents with a trivial task that does not use MCP tools.
4. Wait for them to complete.
5. Call `close_agent` for each subagent.
6. Wait for cleanup.
7. Check the `codex app-server` child process tree again.
8. Repeat with another batch of 10 subagents.

## Observed Results

Before the large test:

- app-server descendants: `46`
- total RSS under app-server: about `2.9 GiB`
- total PSS under app-server: about `1.6 GiB`
- MCP bundles: about `4`

After spawning and closing 10 subagents:

- app-server descendants: `156`
- total RSS: about `7.9 GiB`
- total PSS: about `3.6 GiB`
- MCP bundles: about `14`

After spawning and closing another 10 subagents:

- app-server descendants: `266`
- total RSS: about `11.7 GiB`
- swap usage grew to about `6.4 GiB`
- MCP bundles: about `24`

The growth matched the number of spawned subagents. In the reduced setup each
additional subagent created another set of MCP-related processes, including
Serena, Telegram, and YouTrack/mcp-remote process trees.

## Expected Behavior

After a subagent finishes and is closed:

- MCP processes created for that subagent should be terminated, or
- subagents should reuse a shared project/app-server MCP process pool, or
- Codex should allow subagents to start without inheriting all MCP servers from
  the parent session.

Repeated subagent usage should return to a bounded baseline instead of
accumulating MCP process stacks.

## Actual Behavior

Subagent creation eagerly starts MCP process stacks, even when the subagent task
does not call MCP tools.

Those MCP child trees are not reliably cleaned up after subagent completion and
close, causing linear process and memory growth.

## Workaround / Diagnostic Tool

I wrote a Linux-only diagnostic/workaround tool:

https://github.com/lostfrxks/codex-mcp-clean

It snapshots a selected Codex app-server PID and later reports or kills only MCP
launcher subtrees created after that snapshot. Returning memory/process count to
baseline after killing those subtrees suggests stale MCP child trees are the
source of the growth.

## Related Issues

- #17574
- #17832
- #20883
- #21984
- #24347
```
