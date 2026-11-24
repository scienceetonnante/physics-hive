# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fastapi>=0.115",
#     "uvicorn>=0.30",
#     "jinja2>=3.1",
#     "python-multipart>=0.0.9",
#     "markdown-it-py>=3",
#     "mdit-py-plugins>=0.4",
#     "huggingface_hub[oauth]>=1.16",
#     "pyyaml>=6",
# ]
# ///
# These dependencies are those of space/requirements.txt (tests/test_serve.py checks it); keep them the same.
"""Run the Space on a workspace folder of this machine, to read and answer in a browser.

It serves the Space app from the workspace's own method copy
(.physics-hive/space/) in local mode: it reads the folder directly and writes
your answers, ticks and edits into its files without committing them; the next
`session.py start` commits them as yours. The Space it serves has no sign-in
and listens on this machine only (127.0.0.1): every edit is made in the name
given by --user. Press Ctrl+C to stop it.

Inside a workspace:
  uv run .physics-hive/scripts/serve.py
From a clone of the PhysicsHive repository:
  uv run scripts/serve.py --dir examples/pendulum --read-only
A workspace without a method copy is served with the app next to this script.
"""

from __future__ import annotations

import argparse
import getpass
import os
import socket
import subprocess
import sys
from pathlib import Path

PREFERRED_PORT = 7860  # the port of the Space on the Hub
HOST = "127.0.0.1"
# The host names a request may carry (the app refuses others, which stops a page of another site that makes its
# name point to this machine). Starlette compares them without the port.
ALLOWED_HOSTS = "127.0.0.1,localhost"


class ServeError(SystemExit):
    def __init__(self, message: str):
        super().__init__(f"ERROR: {message}")


def find_workspace(given: str | None) -> Path:
    """The workspace folder: --dir, else the current folder or the nearest parent that is a workspace."""
    if given:
        root = Path(given).expanduser().resolve()
        if not root.is_dir():
            raise ServeError(f"{root} does not exist.")
        if not (root / "project.toml").is_file():
            raise ServeError(f"{root} is not a PhysicsHive workspace (it has no project.toml). "
                             "Name a workspace folder with --dir.")
        return root
    here = Path.cwd().resolve()
    for folder in (here, *here.parents):
        if (folder / "project.toml").is_file():
            return folder
    raise ServeError(f"{here} is not in a PhysicsHive workspace (no project.toml here or above). "
                     "Run this command in a workspace folder, or name one with --dir.")


def app_folder(root: Path) -> Path:
    """The Space app to serve: the workspace's method copy, else the one next to this script."""
    for folder in (root / ".physics-hive" / "space", Path(__file__).resolve().parents[1] / "space"):
        if (folder / "app.py").is_file():
            return folder
    raise ServeError(f"found no Space app (space/app.py) in {root / '.physics-hive'} or next to this script.")


def default_user(root: Path) -> str:
    """The name edits are made in: git's user.name for the workspace, else the login name."""
    try:
        name = subprocess.run(["git", "-C", str(root), "config", "user.name"], capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        name = ""
    if name:
        return name
    try:
        return getpass.getuser()
    except Exception:  # no login name in some containers
        return "lead"


def open_socket(port: int | None) -> socket.socket:
    """A listening socket on HOST: on `port` if given, else on PREFERRED_PORT if free, else on any free port."""
    def bind(number: int) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # as uvicorn does, to restart right after a stop
        try:
            sock.bind((HOST, number))
        except OSError:
            sock.close()
            raise
        sock.listen(128)
        return sock

    if port is not None:
        try:
            return bind(port)
        except OSError as exc:
            raise ServeError(f"cannot listen on port {port} ({exc.strerror}). Another program may use it: "
                             "choose another port with --port, or leave --port out to take a free one.") from None
    try:
        return bind(PREFERRED_PORT)
    except OSError:
        return bind(0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", help="the workspace folder (default: the current folder)")
    parser.add_argument("--port", type=int, help=f"the port to listen on (default: {PREFERRED_PORT} if it is free, "
                        "else any free port)")
    parser.add_argument("--user", help="the name your edits are made in (default: git's user.name, else your "
                        "login name)")
    parser.add_argument("--read-only", action="store_true", help="show the workspace without letting anyone edit it")
    args = parser.parse_args()

    root = find_workspace(args.dir)
    space = app_folder(root)
    user = args.user or default_user(root)
    os.environ["PHYSICS_HIVE_LOCAL"] = str(root)
    os.environ["PHYSICS_HIVE_LOCAL_USER"] = user
    if args.read_only:
        os.environ["PHYSICS_HIVE_READONLY"] = "1"
    os.environ["PHYSICS_HIVE_ALLOWED_HOSTS"] = ALLOWED_HOSTS
    sock = open_socket(args.port)
    port = sock.getsockname()[1]

    import uvicorn

    sys.path.insert(0, str(space))  # app.py imports backend.py and latex.py by plain name
    config = uvicorn.Config("app:app", host=HOST, port=port, log_level="warning")
    server = uvicorn.Server(config)
    print(f"Serving the Space on {root}", flush=True)
    if space != root / ".physics-hive" / "space":
        print(f"  with the app in {space}, because the workspace has no method copy (.physics-hive/)", flush=True)
    print(f"  edits are made as {user}" if not args.read_only else "  read only: nobody can edit", flush=True)
    print(f"Open http://{HOST}:{port}/ in your browser. Press Ctrl+C to stop.", flush=True)
    try:
        server.run(sockets=[sock])
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
    print("Stopped.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
