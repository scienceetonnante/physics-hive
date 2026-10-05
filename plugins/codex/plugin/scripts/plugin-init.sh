#!/usr/bin/env bash
#
# plugin-init.sh — run the bundled PhysicsIntern initializer through uv.
#
# The plugin's init-physics-intern command asks the user its questions in the
# chat (what to do, which harnesses, where, the organisation and project name
# or the repository to join) and calls this script once with the answers as
# flags. The script runs scripts/init.py from the plugin's own copy of the
# method (commons/, hosts/, scripts/, VERSION, vendored by the build script),
# which also accepts --list-harnesses and --list-orgs.
#
# Usage: plugin-init.sh --mode local|create|join --harness <list> --dir <folder>
#                       [--org ORG --name NAME | --repo ORG/NAME] --yes

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: PhysicsIntern needs uv to run its scripts. Install it with:" >&2
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh     (or: brew install uv)" >&2
  exit 1
fi

exec uv run --quiet "$ROOT/scripts/init.py" "$@"
