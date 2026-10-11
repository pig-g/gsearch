#!/usr/bin/env bash
# Install the gsearch OpenCode integration (skill + tool plugin).
#
#   ./install.sh            # install into ~/.config/opencode
#   OPENCODE_CONFIG_DIR=/path ./install.sh
#
# Installs:
#   <config>/skills/gsearch/SKILL.md        -> skill: teaches agents to use gsearch
#   <config>/plugins/gsearch/index.ts       -> tool: exposes google_search
#
# A running OpenCode server picks these up automatically (the config
# directory is watched) or after `opencode service restart`.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${OPENCODE_CONFIG_DIR:-$HOME/.config/opencode}"

if ! command -v gsearch >/dev/null 2>&1; then
  echo "warning: 'gsearch' is not on PATH." >&2
  echo "         Install it first: pipx install .  (or pip install .)" >&2
  echo "         The plugin resolves it at runtime; set GSEARCH_BIN to override." >&2
fi

mkdir -p "$CONFIG/skills/gsearch" "$CONFIG/plugins/gsearch"
cp "$HERE/skill/SKILL.md"     "$CONFIG/skills/gsearch/SKILL.md"
cp "$HERE/plugin/index.ts"    "$CONFIG/plugins/gsearch/index.ts"

echo "installed:"
echo "  $CONFIG/skills/gsearch/SKILL.md"
echo "  $CONFIG/plugins/gsearch/index.ts"
echo
echo "Restart OpenCode to load the tool:  opencode service restart"