# demo-agents-sdk — agent rules

Read [DEMO_INVARIANTS.md](DEMO_INVARIANTS.md) before acting. The vendored
file carries the rules that must hold in every checkout and worktree.
When this repository sits under `projects/demos`, `../AGENTS.md` applies
additionally. In that workspace, consult `../demo-guidance/README.md`
for recording, video review and publishing.

- Every classification asks the model gateway on `127.0.0.1:18157`:
  `../_demo-kit/model-gateway.py` when recording on the host,
  `gateway/fixture_gateway.py` (replay only) in the runners and on nodes.
  Fixture replay is the default. Start with the Models section in
  `../_demo-kit/README.md` and run `just check` before committing.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
