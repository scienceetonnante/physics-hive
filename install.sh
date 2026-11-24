#!/bin/sh
# Create or join a PhysicsHive workspace from a released version of the method.
#
#   curl -LsSf https://raw.githubusercontent.com/scienceetonnante/physics-hive/master/install.sh | sh
#
# It checks for git and uv (and offers to install uv), downloads the method into
# a temporary folder, and runs its init script in the current folder. The
# workspace keeps its own copy of the method, so nothing stays installed.
#
# Options after `sh -s --` go to the init script, for example:
#   curl -LsSf <this url> | sh -s -- --mode join --repo our-lab/physics-hive-x-correction
#   curl -LsSf <this url> | sh -s -- --upgrade          (inside a workspace)
#   curl -LsSf <this url> | sh -s -- --help             (every option)
#
# Environment:
#   PHYSICS_HIVE_VERSION  a release tag (v0.5.0) or a branch (master); default: the latest release
#   PHYSICS_HIVE_REPO     where to download from; default: the GitHub repository
#
# To develop the method, run ./init-physics-hive.sh from a clone instead: it uses
# the method as it is in the clone, uncommitted changes included.

set -eu

REPO="${PHYSICS_HIVE_REPO:-https://github.com/scienceetonnante/physics-hive}"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

# With `curl ... | sh`, standard input is this script, so answers are read from the terminal.
if [ -t 0 ]; then
    INPUT=""
elif (exec </dev/tty) 2>/dev/null; then
    INPUT=/dev/tty
else
    INPUT=none
fi

ask_yes() {
    [ "$INPUT" = none ] && return 1
    printf '%s [Y/n] ' "$1"
    if [ -n "$INPUT" ]; then read -r reply <"$INPUT" || reply=""; else read -r reply || reply=""; fi
    case "$reply" in [Nn]*) return 1 ;; *) return 0 ;; esac
}

command -v git >/dev/null 2>&1 || fail "PhysicsHive needs git. Install it first (on macOS: xcode-select --install)."

UV_INSTALLED=""
if ! command -v uv >/dev/null 2>&1; then
    echo "PhysicsHive runs its scripts with uv (https://docs.astral.sh/uv/), which is not installed."
    ask_yes "Install uv now?" || fail "install uv (curl -LsSf https://astral.sh/uv/install.sh | sh), then run this again."
    curl -LsSf https://astral.sh/uv/install.sh | sh || fail "the installation of uv failed (see above)."
    PATH="${XDG_BIN_HOME:-$HOME/.local/bin}:$PATH"
    command -v uv >/dev/null 2>&1 || fail "uv was installed but is not on the PATH; open a new terminal and run this again."
    UV_INSTALLED=yes
fi

VERSION="${PHYSICS_HIVE_VERSION:-}"
if [ -z "$VERSION" ]; then
    TAGS=$(git ls-remote --tags --refs --sort=-v:refname "$REPO" 'refs/tags/v*') ||
        fail "could not list the releases at $REPO. Check the network connection."
    VERSION=$(printf '%s\n' "$TAGS" | head -n 1 | sed 's|.*refs/tags/||')
    [ -n "$VERSION" ] || fail "found no release at $REPO (set PHYSICS_HIVE_VERSION=master to use the development branch)."
fi

TMP=$(mktemp -d "${TMPDIR:-/tmp}/physics-hive.XXXXXX") || fail "could not create a temporary folder."
trap 'rm -rf "$TMP"' EXIT
trap 'exit 130' HUP INT TERM  # so that the line above also runs on Ctrl+C
git -c advice.detachedHead=false clone --quiet --depth 1 --branch "$VERSION" "$REPO" "$TMP/physics-hive" ||
    fail "could not download PhysicsHive $VERSION from $REPO."
echo "Downloaded PhysicsHive $VERSION."

# The init script reads its answers from the terminal; without one, it asks nothing and takes the defaults.
export PHYSICS_HIVE_PROG="install.sh"  # the name its --help shows
STATUS=0
case "$INPUT" in
    /dev/tty) uv run --quiet "$TMP/physics-hive/scripts/init.py" "$@" </dev/tty || STATUS=$? ;;
    none) uv run --quiet "$TMP/physics-hive/scripts/init.py" "$@" </dev/null || STATUS=$? ;;
    *) uv run --quiet "$TMP/physics-hive/scripts/init.py" "$@" || STATUS=$? ;;
esac
if [ -n "$UV_INSTALLED" ]; then
    echo "uv was installed in this run. Open a new terminal before you launch your harness, so that it finds uv."
fi
exit "$STATUS"
