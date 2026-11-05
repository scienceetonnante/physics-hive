#!/usr/bin/env bash
#
# build-opencode-plugin.sh — assemble the publishable OpenCode plugin from this repo.
#
# Source of truth lives here: commons/, hosts/, scripts/, space/ and VERSION (the method) and
# plugins/opencode/ (the authored files: README.md, install.sh, the global
# /init-physics-hive command, and plugin-init.sh).
#
# This script writes a COMPLETE, self-contained tree into the output dir, which
# is the working copy of the separate `physics-hive-opencode-plugin` repo you
# commit and push to publish. The output dir is a pure build artifact — never
# hand-edit it; edit the sources here and rebuild.
#
# Unlike Claude/Codex there is no marketplace: distribution is a global command
# file + a vendored scaffolder kit installed by install.sh (see plugins/opencode/README.md).
#
# Usage: build-opencode-plugin.sh [output-dir]
#   output-dir defaults to ../physics-hive-opencode-plugin

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$REPO/../physics-hive-opencode-plugin}"
SRC="$REPO/plugins/opencode"

if [[ ! -d "$SRC" ]]; then
  echo "Error: $SRC not found." >&2
  exit 1
fi

# rsync excludes build cruft (__pycache__, .DS_Store) so it never ships.
EXCLUDES=(--exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' --exclude='.pytest_cache')

# 1. Authored files: README.md, install.sh, and the kit (commands/ + scripts/).
mkdir -p "$OUT"
cp "$SRC/README.md" "$OUT/README.md"
cp "$SRC/install.sh" "$OUT/install.sh"
rm -rf "$OUT/physics-hive"
rsync -a "${EXCLUDES[@]}" "$SRC/physics-hive/" "$OUT/physics-hive/"

# Vendor the method from the single source of truth: every host (a workspace
# created here may be opened with any harness, and people who join render from
# its copy), the workspace scripts (next to plugin-init.sh), the Space app and
# VERSION. scripts/init.py copies all of it into each workspace's .physics-hive/.
for part in commons hosts scripts space; do
  if [[ -d "$REPO/$part" ]]; then
    rsync -a "${EXCLUDES[@]}" "$REPO/$part/" "$OUT/physics-hive/$part/"
  fi
done
cp "$REPO/VERSION" "$OUT/physics-hive/VERSION"

echo "Built OpenCode plugin → $OUT"
echo
echo "Publish steps:"
echo "  1. cd \"$OUT\" && git add -A && git commit -m \"...\" && git push"
echo "  2. Ensure the published repo is PUBLIC (git clone over HTTPS must work)."
