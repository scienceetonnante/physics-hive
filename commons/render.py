#!/usr/bin/env python3
"""Render the harness files of a PhysicsIntern workspace for one or more harnesses.

Usage:
  render.py --hosts=claude,opencode --target=<workspace dir>

Reads the host-agnostic method under commons/ (workspace doc, agent roles,
skill workflows) and the glue under hosts/<host>/, and writes into the target:

- AGENTS.md: the method, followed by one short section per selected harness
  (dispatch syntax, tool names). Codex, OpenCode and Pi read it directly.
- CLAUDE.md: one line, `@AGENTS.md`, when Claude Code is selected.
- For each harness, its agent role files, skill files and settings files, in
  its own folder (.claude/, .codex/ + .agents/skills/, .opencode/, .pi/).

Skill bodies are identical for every harness, so a harness that also reads
another harness's skill folder (OpenCode reads .claude/skills/ and
.agents/skills/) sees the same text. Rendered files are personal to each
checkout and git-ignored; this script only writes harness files, never
research content.

Requires Python 3.11+ (stdlib `tomllib`); no third-party packages.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tomllib
from pathlib import Path
from typing import Any

COMMONS = Path(__file__).resolve().parent  # this script lives in commons/
HOSTS = COMMONS.parent / "hosts"
HOST_ORDER = ["claude", "codex", "opencode", "pi"]


# ----- frontmatter parsing -----
#
# Minimal YAML-frontmatter parser for the manifests of commons/agents/*.md and
# commons/skills/*.md: top-level scalars, flow-style lists (`key: [a, b]`) and
# block-style lists. The workspace scripts use PyYAML; the renderer stays
# stdlib-only so it runs with a bare python3.

def _coerce(value: str) -> Any:
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
        return v[1:-1]
    if v == "true":
        return True
    if v == "false":
        return False
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    return v


def _parse_flow_list(value: str) -> list[Any]:
    inner = value.strip()[1:-1].strip()
    if not inner:
        return []
    return [_coerce(item) for item in inner.split(",")]


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse `---`-delimited frontmatter. Returns (metadata, body)."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        end_eof = text.find("\n---", 4)
        if end_eof == -1 or text[end_eof + 4:].strip():
            raise ValueError("Frontmatter opened with --- but no closing --- found")
        header, body = text[4:end_eof], ""
    else:
        header, body = text[4:end], text[end + 5:]

    meta: dict[str, Any] = {}
    lines = header.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if not m:
            raise ValueError(f"Unparseable frontmatter line: {line!r}")
        key, rest = m.group(1), m.group(2).strip()
        if rest == "":
            items = []
            j = i + 1
            while j < len(lines) and lines[j].startswith("  - "):
                items.append(_coerce(lines[j][4:]))
                j += 1
            meta[key] = items if items else ""
            i = j if items else i + 1
            continue
        meta[key] = _parse_flow_list(rest) if rest.startswith("[") and rest.endswith("]") else _coerce(rest)
        i += 1
    return meta, body


def read_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    return parse_frontmatter(path.read_text())


# ----- placeholder substitution -----

def substitute(text: str, ctx: dict) -> str:
    """Replace {{key}} placeholders with values from ctx. Unknown keys raise."""
    def repl(m: re.Match) -> str:
        key = m.group(1).strip()
        if key in ctx:
            return str(ctx[key])
        raise KeyError(f"Unknown placeholder: {{{{{key}}}}}")
    return re.sub(r"\{\{\s*([a-z_]+)\s*\}\}", repl, text)


# ----- frontmatter emission -----

_YAML_RESERVED_STARTERS = set("?:,[]{}#&*!|>'\"%@`")
_YAML_RESERVED_WORDS = {"true", "false", "null", "yes", "no", "on", "off", "~"}
_NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?([eE][+-]?\d+)?$")


def yaml_scalar(value) -> str:
    """Format a value as a YAML scalar, quoting only when the plain form is ambiguous."""
    if isinstance(value, bool):
        return "true" if value else "false"
    s = str(value)
    if not s:
        return '""'
    needs_quotes = (
        s[0] in _YAML_RESERVED_STARTERS
        or s[0].isspace()
        or s[-1].isspace()
        or s.lower() in _YAML_RESERVED_WORDS
        or bool(_NUMERIC_RE.match(s))
        or ": " in s
        or " #" in s
    )
    if not needs_quotes:
        return s
    if '"' not in s:
        return f'"{s}"'
    return "'" + s.replace("'", "''") + "'"


def _emit_yaml(fields: list[tuple[str, object]]) -> str:
    lines = ["---"] + [f"{key}: {yaml_scalar(value)}" for key, value in fields] + ["---"]
    return "\n".join(lines)


def render_tools(capabilities: list[str], host: dict) -> str:
    """Map capabilities to the host's tool names, deduplicated in first-seen order."""
    seen: dict[str, None] = {}
    for cap in capabilities:
        mapped = host["tools_map"].get(cap)
        if mapped is None:
            raise KeyError(f"Capability {cap!r} not in tools_map for {host['name']}")
        seen.setdefault(mapped, None)
    return ", ".join(seen)


def toml_basic_string(s: str) -> str:
    escaped = (
        s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    )
    return f'"{escaped}"'


# ----- agents -----

def render_agent_frontmatter(meta: dict, host: dict) -> str:
    fields: dict[str, Any] = {"name": meta["name"], "description": meta["description"]}
    if "capabilities" in meta:
        fields["tools"] = render_tools(meta["capabilities"], host)
    # Pi uses `output:`; agents whose output path is computed at runtime omit it.
    if meta.get("output_pattern"):
        fields["output"] = meta["output_pattern"]
    for key, value in host.get("agent_extra_fields", {}).items():
        fields[key] = value
    lines = ["---"]
    for key in host["agent_frontmatter_order"]:
        if key in fields:
            lines.append(f"{key}: {yaml_scalar(fields[key])}")
    lines.append("---")
    return "\n".join(lines)


def _render_agent_yaml_md(meta: dict, body: str, host: dict, target: Path) -> None:
    prefix = substitute(host.get("agent_body_prefix", ""), {**host, "name_cap": meta["name"].capitalize()})
    content = f"{render_agent_frontmatter(meta, host)}\n\n{prefix}{body.lstrip()}"
    out_path = target / host["agents_dir"] / f"{meta['name']}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content)


def _render_agent_toml(meta: dict, body: str, host: dict, target: Path) -> None:
    """Codex role file: name, description and the role prompt as developer_instructions.

    The prompt goes in a TOML multi-line basic string, where backslashes are
    escape sequences, so LaTeX in a role (`\\documentclass`) is escaped first.
    """
    if '"""' in body:
        raise ValueError(f"Agent body for {meta['name']!r} contains a triple quote")
    instructions = body.strip().replace("\\", "\\\\")
    lines = [
        f"name = {toml_basic_string(meta['name'])}",
        f"description = {toml_basic_string(meta['description'])}",
        "",
        'developer_instructions = """',
        instructions,
        '"""',
        "",
    ]
    text = "\n".join(lines)
    if tomllib.loads(text)["developer_instructions"].strip() != body.strip():
        raise ValueError(f"Agent body for {meta['name']!r} does not survive the TOML round trip")
    out_path = target / host["agents_dir"] / f"{meta['name']}.toml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)


def render_agents(host: dict, target: Path) -> int:
    count = 0
    for src_path in sorted((COMMONS / "agents").glob("*.md")):
        meta, body = read_frontmatter(src_path)
        body = substitute(body, host)
        if host.get("agent_format", "yaml_md") == "toml":
            _render_agent_toml(meta, body, host, target)
        else:
            _render_agent_yaml_md(meta, body, host, target)
        count += 1
    return count


# ----- skills -----

def _render_skill_nested(meta: dict, body: str, host: dict, target: Path) -> None:
    """<skills_dir>/<name>/SKILL.md — Claude Code, Codex and OpenCode."""
    fields: list[tuple[str, object]] = [("name", meta["name"]), ("description", meta["description"])]
    if host.get("skill_argument_hint") and meta.get("arguments_hint"):
        fields.append(("argument-hint", meta["arguments_hint"]))
    out_path = target / host["skills_dir"] / meta["name"] / "SKILL.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(f"{_emit_yaml(fields)}\n\n{body.lstrip()}")


def _pi_stub_body(meta: dict, host: dict) -> str:
    agent = meta.get("agent")
    agents_used_line = f"Agents used: `{agent}`." if agent else "Agents used: none (runs in the coordinator's context)."
    ctx = {
        "title": meta["name"].replace("-", " ").capitalize(),
        "name": meta["name"],
        "agents_used_line": agents_used_line,
    }
    return substitute(host["skill_stub_template"], ctx)


def _render_skill_pi(meta: dict, body: str, host: dict, target: Path) -> None:
    """Pi: a thin stub under .pi/skills/ for discovery, the workflow under .pi/prompts/."""
    name = meta["name"]
    stub_path = target / host["skills_dir"] / name / "SKILL.md"
    stub_path.parent.mkdir(parents=True, exist_ok=True)
    stub_fields = [("name", name), ("description", meta["description"])]
    stub_path.write_text(f"{_emit_yaml(stub_fields)}\n\n{_pi_stub_body(meta, host)}")

    prompt_fields: list[tuple[str, object]] = [("description", meta["description"])]
    if meta.get("arguments_hint"):
        prompt_fields.append(("args", meta["arguments_hint"]))
    prompt_fields.append(("section", "PhysicsIntern Workflows"))
    if meta.get("top_level_cli", True):
        prompt_fields.append(("topLevelCli", True))
    prompt_body = host.get("preamble", "").lstrip() + "\n" + body.lstrip()
    prompt_path = target / host["prompts_dir"] / f"{name}.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(f"{_emit_yaml(prompt_fields)}\n\n{prompt_body}")


def render_skills(host: dict, target: Path) -> int:
    count = 0
    for src_path in sorted((COMMONS / "skills").glob("*.md")):
        meta, body = read_frontmatter(src_path)
        body = substitute(body, {})  # skill bodies carry no harness-specific values
        if host.get("skills_layout", "nested") == "pi":
            _render_skill_pi(meta, body, host, target)
        else:
            _render_skill_nested(meta, body, host, target)
        count += 1
    return count


# ----- workspace doc, extras -----

def render_workspace_doc(hosts: list[dict], target: Path) -> None:
    sections = "\n\n".join(h["section"].strip() for h in hosts)
    names = ", ".join(h["display_name"] for h in hosts)
    text = substitute((COMMONS / "workspace-doc.md").read_text(), {"harness_sections": sections, "harness_names": names})
    (target / "AGENTS.md").write_text(text)
    if any(h["name"] == "claude" for h in hosts):
        (target / "CLAUDE.md").write_text("@AGENTS.md\n")


def render_host_extras(host: dict, target: Path) -> None:
    """Copy hosts/<host>/extras/<path> to <target>/<path> (settings files)."""
    extras_dir = HOSTS / host["name"] / "extras"
    if not extras_dir.exists():
        return
    for src in extras_dir.rglob("*"):
        if src.is_file() and src.name != ".DS_Store":
            dst = target / src.relative_to(extras_dir)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def clean_host(host: dict, target: Path) -> None:
    """Remove previously rendered agent and skill folders so removed files do not linger."""
    for key in ("agents_dir", "skills_dir", "prompts_dir"):
        if host.get(key):
            folder = target / host[key]
            if folder.is_dir():
                shutil.rmtree(folder)


def load_host(host_name: str) -> dict:
    with (HOSTS / host_name / "host.toml").open("rb") as f:
        host = tomllib.load(f)
    for key, filename in host.pop("file_backed", {}).items():
        path = HOSTS / host_name / filename
        host[key] = path.read_text() if path.exists() else ""
    return host


def parse_hosts(values: list[str]) -> list[str]:
    names: list[str] = []
    for value in values:
        names.extend(v.strip() for v in value.split(",") if v.strip())
    unknown = [n for n in names if n not in HOST_ORDER]
    if unknown:
        raise SystemExit(f"Unknown harness(es): {', '.join(unknown)}. Choose from {', '.join(HOST_ORDER)}.")
    if not names:
        raise SystemExit("Select at least one harness with --hosts.")
    return [n for n in HOST_ORDER if n in names]


def render(host_names: list[str], target: Path) -> str:
    target.mkdir(parents=True, exist_ok=True)
    hosts = [load_host(name) for name in host_names]
    counts = []
    for host in hosts:
        clean_host(host, target)
        n_agents = render_agents(host, target)
        n_skills = render_skills(host, target)
        render_host_extras(host, target)
        counts.append(f"{host['name']} ({n_agents} agents, {n_skills} skills)")
    render_workspace_doc(hosts, target)
    return f"Rendered {', '.join(counts)} + AGENTS.md → {target}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hosts", action="append", default=[], help="comma-separated harnesses: " + ", ".join(HOST_ORDER))
    parser.add_argument("--host", action="append", default=[], help="alias of --hosts")
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()
    message = render(parse_hosts(args.hosts + args.host), args.target.resolve())
    print(message, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
