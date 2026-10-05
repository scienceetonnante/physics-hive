#!/usr/bin/env bash
#
# build-plugin.sh — assemble the publishable Claude Code plugin from this repo.
#
# Source of truth lives here: commons/, hosts/, scripts/, space/ and VERSION (the method) and
# plugins/claude/ (the plugin-specific authored files: marketplace.json,
# plugin.json, the /physics-intern:init command, and plugin-init.sh).
#
# This script writes a COMPLETE, self-contained plugin tree into the output dir,
# which is the working copy of the separate `physics-intern-claude-plugin` repo
# you commit and push to publish. The output dir is a pure build artifact — never
# hand-edit it; edit the sources here and rebuild.
#
# Usage: build-plugin.sh [output-dir]
#   output-dir defaults to ../physics-intern-claude-plugin

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$REPO/../physics-intern-claude-plugin}"
SRC="$REPO/plugins/claude"

if [[ ! -d "$SRC" ]]; then
  echo "Error: $SRC not found." >&2
  exit 1
fi

mkdir -p "$OUT/.claude-plugin"

# 1. Marketplace manifest + repo landing page at the published repo root.
cp "$SRC/.claude-plugin/marketplace.json" "$OUT/.claude-plugin/marketplace.json"
cp "$SRC/README.md" "$OUT/README.md"

# rsync excludes build cruft (__pycache__, .DS_Store) so it never ships.
EXCLUDES=(--exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' --exclude='.pytest_cache')

# 2. Plugin static files (plugin.json, the init command, plugin-init.sh).
rm -rf "$OUT/plugin"
mkdir -p "$OUT/plugin"
rsync -a "${EXCLUDES[@]}" "$SRC/plugin/" "$OUT/plugin/"

# Vendor the method from the single source of truth: every host (a workspace
# created here may be opened with any harness, and people who join render from
# its copy), the workspace scripts (next to plugin-init.sh), the Space app and
# VERSION. scripts/init.py copies all of it into each workspace's .physics-intern/.
for part in commons hosts scripts space; do
  if [[ -d "$REPO/$part" ]]; then
    rsync -a "${EXCLUDES[@]}" "$REPO/$part/" "$OUT/plugin/$part/"
  fi
done
cp "$REPO/VERSION" "$OUT/plugin/VERSION"

echo "Built plugin → $OUT"
echo
echo "Publish steps:"
echo "  1. Bump \"version\" in plugins/claude/plugin/.claude-plugin/plugin.json (then rebuild)."
echo "  2. cd \"$OUT\" && git add -A && git commit -m \"...\" && git push"
