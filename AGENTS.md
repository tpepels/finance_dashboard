# Agent continuation instructions

This repository contains a current operational handoff in [docs/AGENT_HANDOFF.md](docs/AGENT_HANDOFF.md). **Read it before planning any source, ingestion, research, diagnostics, or deployment work.** It records the verified baseline and deliberately unresolved issues. Do not restart the source audit or reimplement completed fixes.

- Work on `main` as requested by the owner; use fast-forward updates and avoid worktrees.
- Treat the local checkout as the source-code workspace and the remote server as the running deployment with its own persistent database and original-source archives.
- Never reset or overwrite production volumes or ingest synthetic/substitute observations to silence scientific source checks. Never commit publisher originals, debug ZIPs containing production diagnostics, credentials, or remote-host configuration.
- Verify the deployed release identity and collect a **post-deployment** diagnostic ZIP before asserting that an older production issue was fixed. A green CI run validates code, not remote ingestion.
- Fix reproducible root causes with tests, run the required checks, and update the handoff's status, last verified commit, and still-open evidence when making further changes.
