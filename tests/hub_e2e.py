# /// script
# dependencies = ["huggingface_hub>=1.0", "pyyaml>=6"]
# ///
"""Live end-to-end test of shared mode on the Hub. Not run by pytest.

It plays the researcher and a second checkout: create a shared space, write the
title and goal of project.md, join it from a second folder, run two sessions in
parallel (each with a reviewed claim, a note and a debrief), merge both (the
second needs a rebase), answer and tick the first debrief through the Space's
own backend against the real Hub, check that the next session receives the
answer and the tick, applies the tick (a result copied into the draft, so the
claim becomes established) and lists it under "Changed by this session", and
abort a session.

It creates private scratch repositories and a private Space under your own
account (named pi-e2e-<timestamp>) and deletes them at the end, unless you pass
--keep. It needs `hf auth login`, uv and git.

Usage: uv run tests/hub_e2e.py [scratch folder] [--keep]
"""
import json, subprocess, sys, tempfile, time
from pathlib import Path
import yaml
from huggingface_hub import HfApi, get_token

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "space"))
args = [a for a in sys.argv[1:] if not a.startswith("--")]
S = Path(args[0]) if args else Path(tempfile.mkdtemp(prefix="pi-e2e-"))
NAME = f"pi-e2e-{int(time.time())}"
ME = HfApi().whoami()["name"]
A, B = S / f"{NAME}-A", S / f"{NAME}-B"
api = HfApi()


def run(cwd, *args, ok=True):
    r = subprocess.run(["uv", "run", "--quiet", *map(str, args)], cwd=cwd, capture_output=True, text=True)
    print(f"$ {' '.join(map(str, args))}  (in {Path(cwd).name}) -> {r.returncode}")
    out = (r.stdout + r.stderr).strip()
    print("   " + out.replace("\n", "\n   ")[:3000])
    if ok and r.returncode:
        raise SystemExit("FAILED")
    return r


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def write(path, meta, body=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{yaml.safe_dump(meta, sort_keys=False).strip()}\n---\n{body}")


def commit(cwd, msg):
    git(cwd, "add", "-A"); git(cwd, "commit", "-q", "-m", msg)


def hubgit(cwd, *args):
    return run(cwd, ".physics-hive/scripts/hubgit.py", *args)


DEBRIEF = """The session checked {card} by {route}.

Read the full note: `sessions/{sid}/note.tex`.

**Question 1.** Is this route enough for now?

> **Answer:**

**Tick what you accept.** The next session applies the ticked lines.

- [ ] Copy Result 1 of note {sid} ({card}) into the draft, as a result.
- [ ] Next step: derive the next order.

#### Anything else for the next session

> **Note:**
"""


def session_work(ws, sid, kind):
    """What a session leaves: an artefact, its claim, a confirming review, a note, a debrief and a handoff."""
    art = run(ws, ".physics-hive/scripts/session.py", "next", kind).stdout.strip()
    card = run(ws, ".physics-hive/scripts/session.py", "next", "CL").stdout.strip()
    route = "derivation" if kind == "D" else "computation"
    write(ws / f"sessions/{sid}/brief.md", {"session": sid, "goal": f"Find X by {route}", "budget": 4}, "## Goal\n")
    run(ws, ".physics-hive/scripts/session.py", "brief")
    if kind == "D":
        write(ws / f"derivations/{art}.summary.md", {"id": art, "kind": "derivation", "supports": [card]}, "## Summary\n")
        (ws / f"derivations/{art}.tex").write_text("\\documentclass{article}\n\\begin{document}x\\end{document}\n")
    else:
        write(ws / f"computations/{art}.md", {"id": art, "kind": "computation", "supports": [card]}, "## Summary\n")
        (ws / f"computations/{art}.py").write_text("print(0.5)\n")
        (ws / f"computations/{art}.out").write_text("0.5\n")
    write(ws / f"claims/{card}.md", {"id": card, "kind": "claim", "statement": f"X = a/2 (by {route})", "depends_on": [],
          "produced_by": {"kind": "agent", "model": "m", "operator": ME}, "session": sid, "supersedes": [], "refutes": []}, "x\n")
    commit(ws, f"[{sid}] {route}({art}): X")
    rpath = run(ws, ".physics-hive/scripts/session.py", "next", "review", art).stdout.strip()
    write(ws / rpath, {"id": Path(rpath).stem, "kind": "review", "target": art, "supports": [card], "claim": "X = a/2",
          "verdict": "confirmed", "by": {"kind": "agent"}, "session": sid, "date": "2026-11-04"}, "## Tests\n")
    commit(ws, f"[{sid}] review: confirmed")
    (ws / f"sessions/{sid}/note.tex").write_text(
        "\\documentclass{article}\\begin{document}\n\\begin{result}[X]\n$X=a/2$.\\card{" + card + "}\n\\end{result}\n\\end{document}\n")
    (ws / f"sessions/{sid}/debrief.md").write_text(DEBRIEF.format(card=card, route=route, sid=sid))
    with open(ws / f"sessions/{sid}/log.md", "a") as log:
        log.write(f"\n## Handoff\n\nNext order open after {sid}.\n")
    commit(ws, f"[{sid}] note, debrief and handoff")
    return card


WS = f"{ME}/physics-hive-{NAME}"  # the workspace dataset; the Space has the same name
repos = [WS, f"{WS}-traces", f"{WS}-sources", f"{WS}-chat-debug"]
space = WS
try:
    # 1. The researcher creates the space.
    run(S, REPO / "scripts/init.py", "--mode", "create", "--org", ME, "--name", NAME, "--harness", "claude",
        "--dir", A, "--yes", "--space-token", "none")
    files = set(api.list_repo_files(space, repo_type="space"))
    assert {"app.py", "backend.py", "latex.py", "latex.css", "README.md", "requirements.txt", "Dockerfile"} <= files, files
    variables = api.get_space_variables(space)
    assert variables["PHYSICS_HIVE_WORKSPACE"].value == WS, variables
    print("Space deployed with", sorted(files))

    # 2. The researcher writes the title and the goal of project.md, and pushes to main.
    text = (A / "project.md").read_text().replace("# <the question in one line>", "# What is X?")
    (A / "project.md").write_text(text.replace("## Goal\n", "## Goal\n\nFind the leading correction to X.\n"))
    commit(A, "Write the question")
    hubgit(A, "push", "-q", "origin", "main")

    # 3. A second checkout joins in another folder.
    run(S, REPO / "scripts/init.py", "--mode", "join", "--repo", WS, "--harness", "opencode", "--dir", B, "--yes")
    assert (B / ".opencode/agents/deriver.md").is_file()

    # 4. Two sessions in parallel; B sees A's.
    run(A, ".physics-hive/scripts/session.py", "start", "--harness", "claude", "--model", "model-a")
    rb = run(B, ".physics-hive/scripts/session.py", "start", "--harness", "opencode", "--model", "model-b")
    sa = json.loads((A / ".active-session").read_text())["id"]
    sb = json.loads((B / ".active-session").read_text())["id"]
    print("sessions:", sa, sb)
    assert "Other open sessions:" in rb.stdout, "B should see A's session"
    assert "Fetching" not in rb.stdout + rb.stderr, "progress bars should be off"
    card_a = session_work(A, sa, "D")
    session_work(B, sb, "C")

    # 5. A ends first; B ends after, which needs a rebase on the new main.
    run(A, ".physics-hive/scripts/session.py", "end")
    run(B, ".physics-hive/scripts/session.py", "end")
    index = (B / "INDEX.md").read_text()
    assert index.count("**CL-") == 2, index
    assert "Changed by this session" in (B / f"sessions/{sb}/debrief.md").read_text()

    # 6. The researcher answers and ticks A's debrief in the Space (its backend, on the real Hub).
    import backend as sb_backend

    space_backend = sb_backend.Backend(sb_backend.HubStore(WS, get_token(), cache=S / "space-cache"))
    space_backend.refresh()
    assert space_backend.error is None, space_backend.error
    debrief = next(d for d in space_backend.debriefs() if d["id"] == sa)
    print(space_backend.save_debrief(ME, sa, {1: "Yes, for now."}, {0}, "Start on the disk.", debrief["text"]))
    print(space_backend.next_session_receives())

    # 7. The next session receives the answer and the tick, applies it, and lists it as changed.
    hubgit(B, "pull", "-q", "origin", "main")
    rc = run(B, ".physics-hive/scripts/session.py", "start", "--harness", "opencode", "--model", "model-b")
    sc = json.loads((B / ".active-session").read_text())["id"]
    assert "Answer: Yes, for now." in rc.stdout and f"✓ Copy Result 1 of note {sa}" in rc.stdout, rc.stdout
    assert "Your note: Start on the disk." in rc.stdout and f"Handoff from {sa}" in rc.stdout
    draft = (B / "draft.tex").read_text()
    (B / "draft.tex").write_text(draft.replace("\\bibliographystyle", "\\begin{result}[X]\n$X=a/2$.\\card{"
                                               + card_a + "}\n\\end{result}\n\n\\bibliographystyle"))
    commit(B, f"[{sc}] apply the lines ticked in the {sa} debrief")
    write(B / f"sessions/{sc}/brief.md", {"session": sc, "goal": "Derive the next order", "budget": 4}, "## Goal\n")
    run(B, ".physics-hive/scripts/session.py", "brief")
    (B / f"sessions/{sc}/note.tex").write_text("\\documentclass{article}\\begin{document}Nothing yet.\\end{document}\n")
    (B / f"sessions/{sc}/debrief.md").write_text("Nothing new.\n\n#### Anything else for the next session\n\n> **Note:**\n")
    commit(B, f"[{sc}] note and debrief")
    run(B, ".physics-hive/scripts/session.py", "end")
    changed = (B / f"sessions/{sc}/debrief.md").read_text()
    assert f"as you ticked in {sa}" in changed, changed
    assert f"**{card_a}** · established" in (B / "INDEX.md").read_text()

    # 8. An aborted session leaves the checkout on main.
    run(A, ".physics-hive/scripts/session.py", "start", "--harness", "claude", "--model", "model-a")
    r = run(A, ".physics-hive/scripts/session.py", "abort")
    assert "uncommitted" not in r.stdout + r.stderr and git(A, "rev-parse", "--abbrev-ref", "HEAD") == "main"

    # 9. What the Hub holds.
    print("main history:", [c.title for c in api.list_repo_commits(WS, repo_type="dataset")][:10])
    print("traces:", sorted(api.list_repo_files(f"{WS}-traces", repo_type="dataset")))
    meta = json.loads(Path(api.hf_hub_download(f"{WS}-traces", f"{sa}/meta.json", repo_type="dataset")).read_text())
    print("meta.json:", {k: meta[k] for k in ("session", "pull_request", "merge_commit", "commits", "trace_note")})
    print("discussions:", [(d.num, d.title, d.status) for d in api.get_repo_discussions(WS, repo_type="dataset")])
    print("ALL CHECKS PASSED")
finally:
    if "--keep" not in sys.argv:
        for repo in repos:
            api.delete_repo(repo, repo_type="dataset", missing_ok=True)
        api.delete_repo(space, repo_type="space", missing_ok=True)
        print("deleted scratch repos")
