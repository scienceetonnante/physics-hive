#!/usr/bin/env bash
#
# init-physics-hive.sh — create, join or refresh a PhysicsHive workspace.
#
# A thin launcher for scripts/init.py, which runs through uv
# (https://docs.astral.sh/uv/) with its dependencies declared inline. Run it
# without options to answer a few questions in the terminal; every question
# also has a flag:
#
#   init-physics-hive.sh [--mode local|create|join] [--harness claude,codex,opencode,pi]
#                          [--dir PATH] [--org ORG --name NAME] [--repo ORG/NAME]
#                          [--question TEXT] [--goal TEXT] [--yes]
#
# Run it inside an existing workspace to add a harness or refresh the rendered
# harness files; add --upgrade to replace the workspace's method copy with
# this one. See `init-physics-hive.sh --help` for every option.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "PhysicsHive needs uv to run its scripts. Install it with:" >&2
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh     (or: brew install uv)" >&2
  exit 1
fi

export PHYSICS_HIVE_PROG="init-physics-hive.sh"  # the name its --help shows
exec uv run --quiet "$SCRIPT_DIR/scripts/init.py" "$@"
