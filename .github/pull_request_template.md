## What this changes and why



## Checklist

- [ ] I ran the render (`python3 commons/render.py --hosts=claude,codex,opencode,pi --target=<new folder>`) and read its output.
- [ ] I ran the tests (`uv run --no-project --with pytest --with httpx --with-requirements space/requirements.txt --with "mcp>=1.12,<2" pytest -q tests/`).
- [ ] I updated `README.md`, the guides in `docs/`, `DOCUMENTATION.md`, `CLAUDE.md` and `ROADMAP.md` where this change needs it.
- [ ] If this changes the method, I bumped `VERSION`.
