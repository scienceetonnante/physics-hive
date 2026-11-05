#!/usr/bin/env bash
#
# install.sh — install the PhysicsHive bootstrap into OpenCode (global).
#
# OpenCode has no plugin marketplace, and its JS plugins can register only tools
# and hooks — not slash commands. So distribution is a global command FILE plus
# a vendored scaffolder kit, copied into your OpenCode config dir:
#
#   ${XDG_CONFIG_HOME:-$HOME/.config}/opencode/commands/init-physics-hive.md
#   ${XDG_CONFIG_HOME:-$HOME/.config}/opencode/physics-hive/   (kit: commons + hosts + script)
#
# After install, /init-physics-hive is available in every project. Re-running
# this script upgrades an existing install in place.
#
# Usage: ./install.sh

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_SRC="$SRC/physics-hive"

if [[ ! -d "$KIT_SRC" ]]; then
  echo "Error: kit not found at $KIT_SRC (run from the plugin repo root)." >&2
  exit 1
fi

CFG="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
CMD_SRC="$KIT_SRC/commands/init-physics-hive.md"

# rsync excludes build cruft so it never lands in the install.
EXCLUDES=(--exclude='__pycache__' --exclude='.DS_Store')

mkdir -p "$CFG/commands"

# 1. The kit (commons/ + hosts/opencode/ + scripts/ + commands/) — the command
#    references the scaffolder at this absolute path, so location is fixed.
rsync -a --delete "${EXCLUDES[@]}" "$KIT_SRC/" "$CFG/physics-hive/"

# 2. The global slash command itself.
cp "$CMD_SRC" "$CFG/commands/init-physics-hive.md"

echo "Installed PhysicsHive into $CFG"
echo "  command: $CFG/commands/init-physics-hive.md"
echo "  kit:     $CFG/physics-hive/"
echo
echo "Next: restart OpenCode, then in a fresh folder for your problem run:"
echo "  /init-physics-hive"
