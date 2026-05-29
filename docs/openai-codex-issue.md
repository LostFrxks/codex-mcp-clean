## Summary

Codex app-server appears to start additional stdio MCP process stacks when spawning subagents. After the subagents complete and `close_agent` is called, some MCP child process trees remain alive under the long-lived `codex app-server`.

This causes process count and memory usage to grow roughly linearly with subagent usage. On my machine this previously caused heavy swap pressure and an OOM/desktop session collapse.

I also created a Linux-only diagnostic/workaround tool that helped confirm the source of the growth:

https://github.com/LostFrxks/codex-mcp-clean

## Environment

- Codex CLI: `codex-cli 0.128.0`
- OS: Ubuntu 24.04.4 LTS
- Kernel: Linux 6.17.0-29-generic x86_64
- Machine: 16 GB RAM, 16 GB swap, 8 CPU cores
- Surface: Codex app-server / IDE integration
- Reduced MCP set during repro:
  - Serena
  - Telegram
  - YouTrack via `mcp-remote`

Heavy MCP servers such as Playwright, Context7, and Slack were disabled for the reduced repro.

## Reproduction Pattern

1. Start Codex app-server with stdio MCP servers enabled.
2. Take a baseline process/memory snapshot of the `codex app-server` child tree.
3. Spawn subagents with trivial tasks that do not use MCP tools.
4. Wait for the subagents to complete.
5. Call `close_agent` for each subagent.
6. Wait briefly for Codex cleanup.
7. Check the `codex app-server` child process tree again.
8. Optionally repeat with larger subagent batches.

## Small Live Repro: 3 Subagents

Before spawning 3 trivial subagents, the selected app-server had:

- `23` descendants
- `6` MCP launcher roots
- RSS around `203 MiB`

After spawning 3 subagents:

- `74` descendants
- `24` MCP launcher roots
- RSS around `3.7 GiB`
- Snapshot report showed `18` new MCP launcher roots / `50` new processes

After all 3 subagents completed and `close_agent` was called for each one, Codex cleaned up part of the process tree, but the snapshot still showed:

- `9` MCP launcher roots
- `33` processes

A dry-run with `codex-mcp-clean cleanup --root-pid <PID>` identified those remaining MCP subtrees. Running the same command with `--kill` terminated them:

```text
TERM sent to 33 processes; SIGKILL fallback attempted for 0
```

After cleanup:

- snapshot report returned to `launcher_roots=0`, `processes_total=0`
- app-server returned to about the previous baseline MCP footprint
- available memory increased back from about `4.7 GiB` to about `6.8 GiB`

## Larger Repro: 10 + 10 Subagents

In an earlier larger run, before the batch:

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

The growth matched the number of spawned subagents.

## Expected Behavior

After a subagent finishes and is closed:

- MCP processes created for that subagent should be terminated, or
- subagents should reuse a shared project/app-server MCP process pool, or
- Codex should allow subagents to start without inheriting all parent-session MCP servers.

Repeated subagent usage should return to a bounded baseline instead of accumulating MCP process stacks.

## Actual Behavior

Subagent creation starts additional MCP process stacks, even when the subagent task does not call MCP tools.

After subagent completion and `close_agent`, some MCP child process trees remain alive under the app-server, causing process and memory growth.

## Diagnostic / Workaround Tool

I wrote a small Linux-only diagnostic/workaround tool:

https://github.com/LostFrxks/codex-mcp-clean

It snapshots a selected Codex app-server PID and later reports or kills only MCP launcher subtrees created after that snapshot.

This is not a proposed upstream fix, but it helped confirm that stale MCP child trees are the source of the memory growth. It also avoids touching other Codex app-server PIDs.

## Related Issues

This looks related to the same defect class as:

- #17574
- #17832
- #20883
- #21984
- #24347

I am opening this separately because this is a Linux app-server reproduction with a reduced MCP set and controlled before/after measurements.

Happy to help with more testing or open a PR if the Codex team wants an external contribution for this fix.
