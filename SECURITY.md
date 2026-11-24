# Security

PhysicsHive is a research prototype. This file says what a shared space trusts, what protects what, and how to report a security problem.


## What a shared space trusts

- **The members of the organisation that owns the space.** Anyone who can sign in to the Space can write in it, and anyone with write access to the workspace repository can commit to it.
- **The agents the contributors run.** They work in the contributor's checkout, with the contributor's Hugging Face login, and what they commit reaches the workspace.
- **Whoever can commit to the workspace, as far as the Space's token goes.** The Space imports the scripts of the workspace's own method copy and compiles the workspace's LaTeX, which can read any file the Space can read. So anyone who can commit to the workspace, including an agent that follows instructions planted in a paper it read, can obtain the Space's token. By default that token is the creator's own login token. [The Space's token](docs/shared-spaces.md#the-spaces-token) explains how to give the Space a dedicated token limited to the organisation's repositories instead.


## What protects what

- **Private repositories.** The five repositories of a space are private: only members of the organisation see them.
- **Sign-in.** The Space is private and asks for a Hugging Face sign-in, so only members can open it.
- **The Space's token.** It is a Space secret. A dedicated fine-grained token limits what a leak of it gives.
- **The path check.** The Space never opens a file whose real location is outside the workspace, a file in `.git`, or a `.env` file, and its checkout of the workspace contains no symbolic links.
- **The harnesses' sandboxes.** With Claude Code's sandbox on (your setting), the workspace's settings let commands reach only the Hub and PyPI. Codex runs in its workspace-write sandbox, with network access. OpenCode does not confine the commands it runs to the workspace. See [Setting up your harness](docs/harness-setup.md).
- **Secrets in traces.** Before a trace is uploaded, the secrets the export recognises are replaced with a marker. This does not guarantee that a trace holds none: see [Traces and secrets](docs/shared-spaces.md#traces-and-secrets), and read the traces before making them public.
- **The Space on your machine.** `serve.py` runs the Space without sign-in. It listens on this machine only (127.0.0.1) and refuses requests that name another host, but another user of the same machine can reach it.

[ROADMAP.md](ROADMAP.md) lists what could be done about the Space running the workspace's code.


## Reporting a problem

If private vulnerability reporting is enabled for this repository on GitHub (the *Security* tab, *Report a vulnerability*), use it. Otherwise, open an issue that says which part is affected, without the sensitive details: no token, and no working exploit.
