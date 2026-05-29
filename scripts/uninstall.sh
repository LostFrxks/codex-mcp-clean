#!/usr/bin/env bash
set -euo pipefail

install_dir="${CODEX_MCP_CLEAN_HOME:-"$HOME/.local/share/codex-mcp-clean"}"
bin_dir="${CODEX_MCP_CLEAN_BIN:-"$HOME/.local/bin"}"
wrapper="$bin_dir/codex-mcp-clean"

rm -f "$wrapper"
rm -rf "$install_dir/venv"

printf 'Removed %s\n' "$wrapper"
printf 'Removed %s/venv\n' "$install_dir"
