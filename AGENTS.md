# Data Product Framework (DPF) — Global Agent Entrypoint

This repository is an agentic, specification-driven Data Product Framework on Google Cloud.
All coding agents (Gemini CLI, Antigravity, Claude Code, Cursor, Cline) MUST load and obey:

1. **[openspec/AGENTS.md](openspec/AGENTS.md)** — Canonical Golden Rules, 5-Tier MCP Tool Selection Hierarchy, Gates `G0`–`G4`, and the Elephant-Goldfish verification rule.
2. **[registry/agent-config.json](registry/agent-config.json)** & **[registry/platform-defaults.yaml](registry/platform-defaults.yaml)** — Active GCP project ID, project number, region, business calendar timezone, service accounts, and optional `presentation_server_url` hydrated on first run.
3. **[.agents/skills.json](.agents/skills.json)** & **[.agents/skills/](.agents/skills/)** — Agent skills (`assess-use-case`, `goldfish-verify`, `author-brd`, `validate-brd`, `resolve-tdd`, `compose-pipeline`, `render-engine-artefacts`, `test-data-product`, `trace-coverage`, `monitor-data-product`, `publish-data-product`, `register-knowledge-catalog`).

## Workspace Bootstrap vs. Product Compilation

* **Layer 0 — Workspace Foundation (`bootstrap/terraform/` via `bootstrap/deploy.sh` or `bootstrap/deploy-existing-project.sh`)**:
  Provisions (or attaches to) the Google Cloud project, enables required APIs, creates Google-managed service agents, creates `dataform-runner` and `dpf-monitor` service accounts via keyless impersonation, provisions the default Dataform repository and state bucket, and writes outputs to `registry/agent-config.json` and `registry/platform-defaults.yaml`. Never run `terraform destroy` without explicit human confirmation.
* **Layer 1..N — Per-Product Artefacts (`generated/<product>/` via `dpf generate <product>`)**:
  Generated deterministically from `products/<id>/product.yaml` (or worked examples in `examples/<id>/product.yaml`). Never hand-edit files inside `generated/` or `tests/golden/`.

## First-Time Template Setup

If this repository was just created from the GitHub Template, follow **[bootstrap/README.md](bootstrap/README.md)** or execute `@bootstrap/onboarding-prompt.md`.
