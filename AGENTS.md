# demo-agents-sdk — agent rules

> **Directory-wide rules apply.** Read [`../AGENTS.md`](../AGENTS.md) first —
> it governs every demo in `projects/demos/`. For anything involving a screen
> recording, a finished video, publishing copy, or a launch, read
> [`../demo-guidance/README.md`](../demo-guidance/README.md) before acting.
> `_demo-kit` runs before you record; `demo-guidance` runs after.

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
