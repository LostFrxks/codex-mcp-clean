#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  printf 'codex-mcp-clean is Linux-only.\n' >&2
  exit 1
fi

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
install_dir="${CODEX_MCP_CLEAN_HOME:-"$HOME/.local/share/codex-mcp-clean"}"
venv_dir="$install_dir/venv"
bin_dir="${CODEX_MCP_CLEAN_BIN:-"$HOME/.local/bin"}"
wrapper="$bin_dir/codex-mcp-clean"

mkdir -p "$bin_dir"
if python3 -m venv "$venv_dir" >/dev/null 2>&1; then
  "$venv_dir/bin/python" -m pip install --upgrade pip >/dev/null
  "$venv_dir/bin/python" -m pip install "$repo_dir"

  cat >"$wrapper" <<EOF
#!/usr/bin/env bash
exec "$venv_dir/bin/codex-mcp-clean" "\$@"
EOF
  install_mode="venv"
else
  rm -rf "$venv_dir"
  cat >"$wrapper" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="$repo_dir\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m codex_mcp_clean.cli "\$@"
EOF
  install_mode="source-wrapper"
fi
chmod +x "$wrapper"

printf 'Installed codex-mcp-clean to %s (%s)\n' "$wrapper" "$install_mode"
if [[ "$install_mode" == "source-wrapper" ]]; then
  printf 'Note: python3-venv is unavailable, so the wrapper points at this checkout.\n'
  printf 'Keep this directory in place, or install python3-venv and rerun this script.\n'
fi
printf 'Run: codex-mcp-clean --version\n'
