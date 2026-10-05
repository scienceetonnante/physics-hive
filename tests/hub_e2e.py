# /// script
# dependencies = ["huggingface_hub>=1.0", "pyyaml>=6"]
# ///
"""Live end-to-end test of shared mode on the Hub. Not run by pytest.

It plays a lead and a second operator in two checkouts: create a shared space,
write the problem and a hand-written claim, join it, run two sessions in
parallel that both add evidence to that claim, merge both (the second needs a
rebase), check that a promotion is refused for a non-lead and accepted for the
lead, open a plan proposal, and abort a session.

It creates private scratch repositories under your own account (named
pi-e2e-<timestamp>) and deletes them at the end, unless you pass --keep. It
needs `hf auth login` and uv.

Usage: uv run tests/hub_e2e.py [scratch folder] [--keep]
"""
import json, os, subprocess, sys, tempfile, time
from pathlib import Path
import yaml
from huggingface_hub import HfApi

REPO = Path(__file__).resolve().parents[1]
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
    return run(cwd, ".physics-intern/scripts/hubgit.py", *args)


repos = [f"{ME}/{NAME}", f"{ME}/{NAME}-traces", f"{ME}/{NAME}-sources", f"{ME}/{NAME}-chat-debug"]
try:
    # 1. The lead creates the space.
    run(S, REPO / "scripts/init.py", "--mode", "create", "--org", ME, "--name", NAME, "--harness", "claude",
        "--dir", A, "--yes", "--space-token", "none")
    # 2. The lead writes the problem and a hand-written claim, and pushes to main.
    (A / "problem.md").write_text("# Problem\n\nFind the leading correction to X.\n")
    hid = f"CL-{ME}-20261005T120000"
    write(A / f"claims/{hid}.md", {"id": hid, "kind": "claim", "statement": "X = a/2 to leading order",
          "depends_on": [], "produced_by": {"kind": "human", "user": ME}, "session": None,
          "supersedes": [], "refutes": [], "answers": []}, "A hand result by the lead.\n")
    commit(A, "Problem and a first claim")
    hubgit(A, "push", "-q", "origin", "main")

    # 3. A second operator joins in another folder.
    run(S, REPO / "scripts/init.py", "--mode", "join", "--repo", f"{ME}/{NAME}", "--harness", "opencode", "--dir", B, "--yes")
    assert (B / ".opencode/agents/deriver.md").is_file() and (B / f"claims/{hid}.md").is_file()

    # 4. Two sessions in parallel, both adding evidence to the same claim.
    ra = run(A, ".physics-intern/scripts/session.py", "start", "--harness", "claude", "--model", "model-a")
    rb = run(B, ".physics-intern/scripts/session.py", "start", "--harness", "opencode", "--model", "model-b")
    sa = json.loads((A / ".active-session").read_text())["id"]
    sb = json.loads((B / ".active-session").read_text())["id"]
    print("sessions:", sa, sb)
    assert "Other open sessions (1)" in rb.stdout, "B should see A's session"
    assert "Fetching" not in rb.stdout + rb.stderr, "progress bars should be off"

    for ws, sid, kind in ((A, sa, "D"), (B, sb, "C")):
        art = run(ws, ".physics-intern/scripts/session.py", "next", kind).stdout.strip()
        write(ws / f"sessions/{sid}/brief.md", {"session": sid, "goal": f"Check {hid} by {'derivation' if kind == 'D' else 'computation'}",
              "budget": 4, "merge": "auto", "starts_from": [hid]}, "## Goal\n")
        run(ws, ".physics-intern/scripts/session.py", "brief")
        if kind == "D":
            write(ws / f"derivations/{art}.summary.md", {"id": art, "kind": "derivation", "supports": [hid]}, "## Summary\n")
            (ws / f"derivations/{art}.tex").write_text("\\documentclass{article}\n\\begin{document}x\\end{document}\n")
        else:
            write(ws / f"computations/{art}.md", {"id": art, "kind": "computation", "supports": [hid]}, "## Summary\n")
            (ws / f"computations/{art}.py").write_text("print(0.5)\n")
            (ws / f"computations/{art}.out").write_text("0.5\n")
        commit(ws, f"[{sid}] artefact {art}")
        rpath = run(ws, ".physics-intern/scripts/session.py", "next", "review", art).stdout.strip()
        write(ws / rpath, {"id": Path(rpath).stem, "kind": "review", "target": art, "supports": [hid], "claim": "X = a/2",
              "verdict": "confirmed", "by": {"kind": "agent"}, "session": sid, "date": "2026-10-05"}, "## Tests\n")
        write(ws / f"sessions/{sid}/report.md", {"session": sid, "stop_reason": "goal reached", "dispatches": 2},
              f"## Found\n- {art} supports {hid}\n\n## Proposed promotions\n- {hid}: two routes\n")
        commit(ws, f"[{sid}] review and report")

    # 5. A ends first; B ends after, which needs a rebase on the new main.
    run(A, ".physics-intern/scripts/session.py", "end")
    run(B, ".physics-intern/scripts/session.py", "end")
    index = (B / "INDEX.md").read_text()
    line = next(l for l in index.splitlines() if f"**{hid}**" in l)
    print("INDEX line:", line)
    assert "D-" in line and "C-" in line, "both pieces of evidence should be listed"

    # 6. Promotion: refused for a non-lead, accepted for the lead.
    hubgit(A, "pull", "-q", "origin", "main")
    toml = (A / "project.toml").read_text()
    (A / "project.toml").write_text(toml.replace(f'leads = ["{ME}"]', 'leads = ["somebody-else"]'))
    commit(A, "Temporarily make somebody else the lead"); hubgit(A, "push", "-q", "origin", "main")
    r = run(A, ".physics-intern/scripts/promote.py", hid, "--reason", "two routes", ok=False)
    assert r.returncode != 0 and "not in [people] leads" in (r.stdout + r.stderr)
    (A / "project.toml").write_text(toml)
    commit(A, "Back to the real lead"); hubgit(A, "push", "-q", "origin", "main")
    run(A, ".physics-intern/scripts/promote.py", hid, "--reason", "a derivation and a computation, each reviewed")
    hubgit(A, "pull", "-q", "origin", "main")
    run(A, ".physics-intern/scripts/regen.py")
    assert f"**{hid}** · established" in (A / "INDEX.md").read_text()

    # 7. A plan proposal, the waiting list, and an aborted session.
    r = run(B, ".physics-intern/scripts/session.py", "start", "--harness", "opencode", "--model", "model-b")
    sc = json.loads((B / ".active-session").read_text())["id"]
    (B / f"sessions/{sc}/plan-proposal.md").write_text("# Plan\n\n1. Derive the next order.\n")
    run(B, ".physics-intern/scripts/propose.py", "plan.md", "--from", f"sessions/{sc}/plan-proposal.md")
    r = run(B, ".physics-intern/scripts/session.py", "abort")
    assert "uncommitted" not in r.stdout + r.stderr and git(B, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert "ready to merge" not in run(B, ".physics-intern/scripts/session.py", "status").stdout

    # 8. What the Hub holds.
    print("main history:", [c.title for c in api.list_repo_commits(f"{ME}/{NAME}", repo_type="dataset")][:8])
    print("traces:", sorted(api.list_repo_files(f"{ME}/{NAME}-traces", repo_type="dataset")))
    meta = json.loads(Path(api.hf_hub_download(f"{ME}/{NAME}-traces", f"{sa}/meta.json", repo_type="dataset")).read_text())
    print("meta.json:", {k: meta[k] for k in ("session", "pull_request", "merge_commit", "commits", "trace_note")})
    print("discussions:", [(d.num, d.title, d.status) for d in api.get_repo_discussions(f"{ME}/{NAME}", repo_type="dataset")])
    print("ALL CHECKS PASSED")
finally:
    if "--keep" not in sys.argv:
        for repo in repos:
            api.delete_repo(repo, repo_type="dataset", missing_ok=True)
        print("deleted scratch repos")
