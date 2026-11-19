# Data Product Framework (DPF) — Global Agent Entrypoint

This repository is an agentic, specification-driven Data Product Framework on Google Cloud.
All coding agents (Gemini CLI, Antigravity, Claude Code, Cursor, Cline) MUST load and obey this file, along with:

1. **[framework/project.md](framework/project.md)** — Platform context, Google Cloud naming policy, non-negotiables, and toolchain.
2. **[registry/agent-config.json](registry/agent-config.json)** & **[registry/platform-defaults.yaml](registry/platform-defaults.yaml)** — Active GCP project ID, project number, region, business calendar timezone, service accounts, and optional `presentation_server_url` hydrated on first run.
3. **[.agents/skills.json](.agents/skills.json)** & **[.agents/skills/](.agents/skills/)** — Agent skills (`assess-use-case`, `goldfish-verify`, `author-brd`, `validate-brd`, `resolve-tdd`, `compose-pipeline`, `render-engine-artefacts`, `test-data-product`, `trace-coverage`, `monitor-data-product`, `publish-data-product`, `register-knowledge-catalog`).

## Golden rules

1. **Never write a BRD as an engineer.** Use `framework/skills/author-brd`, which interviews the
   business using the rubric. If an answer is unknown, record a `[NEEDS-DECISION: id]`
   marker — do not invent it.
2. **Never put modelling vocabulary in a BRD.** No grain, SCD, dimension, surrogate key,
   partition or BigQuery in a document a business SME owns.
3. **Derive, then confirm.** Modelling decisions live in the TDD and are played back to
   the business as `playback.md` (or `semantics.md`) in their language.
4. **Cite requirement IDs.** Every TDD decision and manifest element names the BRD
   requirement (or platform capability) it satisfies. Unjustified design fails G1.
5. **Prefer MCP and existing agents.** Before writing integration code, consult
   `registry/mcp_servers.yaml` and the tier order in
   `framework/specs/tool-selection/spec.md`.
6. **Design with an elephant; verify with a goldfish.** Long sessions share your unspoken
   assumptions. Before business sign-off (G1) or accepting a golden diff on custom SQL (G3),
   spawn a fresh, zero-context subagent (`.agents/skills/goldfish-verify`) that sees only the
   artefacts under test — never the chat history or upstream prose.

## Tool selection order (enforced)

| Tier | Use | Example |
|---|---|---|
| 1 | Managed remote MCP server | BigQuery MCP; Knowledge Catalog MCP |
| 2 | Self-hosted MCP server | MCP Toolbox for Databases (Oracle, Postgres, Spanner, ...) |
| 3 | Existing managed agent or API | Conversational Analytics API; Document AI; Datastream API |
| 4 | Official SDK / CLI / Terraform provider | `google-cloud-bigquery`, `bq`, `gcloud`, Terraform |
| 5 | Bespoke code | **Requires an ADR** explaining why tiers 1–4 do not work |

Skills declare their tier in front-matter (`metadata.dpf.tool_tier`). `dpf lint` fails a
skill sitting at tier 4–5 when the registry shows a tier 1–3 option covering one of its
`needs`, and fails bespoke code under `examples/` or `products/` that lacks a
`# dpf: skill=<id> tier=<n> adr=<ADR>` marker naming a real skill and an existing ADR.

## Workspace bootstrap vs. product compilation

* **Layer 0 — Workspace Foundation (`bootstrap/terraform/` via `bootstrap/deploy.sh` or `bootstrap/deploy-existing-project.sh`)**:
  Provisions (or attaches to) the Google Cloud project, enables required APIs, creates Google-managed service agents, creates `dataform-runner` and `dpf-monitor` service accounts via keyless impersonation, provisions the default Dataform repository and state bucket, and writes outputs to `registry/agent-config.json` and `registry/platform-defaults.yaml`. Never run `terraform destroy` without explicit human confirmation.
* **Layer 1..N — Per-Product Artefacts (`generated/<product>/` via `dpf generate <product>`)**:
  Generated deterministically from `products/<id>/product.yaml` (or worked examples in `examples/<id>/product.yaml`). Never hand-edit files inside `generated/` or `tests/golden/`.

## Workflow

```
propose -> BRD -> G0 -> TDD + playback.md + sign-off -> G1 -> compose -> G2
        -> generate -> G3 -> deploy + record evidence -> G4 -> monitor -> (breach) -> change brief
```

| Gate | Passes when | Command |
|---|---|---|
| G0 | the BRD answers the rubric, is approved and uses no modelling vocabulary | `dpf brd validate <product>` |
| G1 | the TDD and manifest resolve every requirement; the sign-off matches the semantic digest | `dpf check <product> --gate G1` |
| G2 | every stage composes from skills and adapters; every scenario (AX) maps to a test (AT) | `dpf check <product> --gate G2` |
| G3 | artefacts generate deterministically, match the golden copy, and every requirement traces to an artefact and a test | `dpf check <product> --gate G3` |
| G4 | every test has passing evidence for the **current** build digest | `dpf check <product> --gate G4` |

Gates are cumulative: `--gate G3` runs G0 to G3. Product specifications live alongside each
product at `products/<product>/specs/brd/` and `products/<product>/specs/tdd/`, and platform
capability specifications live under `framework/specs/<capability>/spec.md`. All specs follow
the DPF spec conventions (`framework/specs/spec-conventions/spec.md`), enforced natively by
`dpf validate`. Changes flow through normal Git pull requests; a TDD-only change that does not
alter `playback.md` or model grain/history needs no business re-approval.

`dpf monitor <product> --open-change` turns a confirmed breach of the observability policy
into a single-file Markdown breach brief (`changes/monitor-<product>-<kind>-<YYYYMMDD-HHMM>.md`)
quoting the breach, affected requirements, runbook link, and verification checklist.

## Never fabricate evidence

Evidence files under `evidence/<product>/` record real runs against a deployed build
(`dpf test run --live`) or real human attestations (`dpf test attest`). Never write one by
hand, never copy one to a new build digest, and never weaken a check to make G4 pass. A
failing G4 is the correct state for a product that has not been run.

## When you are unsure

Ask, or record a `[NEEDS-DECISION]`. A recorded gap is cheap; an invented business rule
is expensive and hard to find later.

## First-time template setup

If this repository was just created from the GitHub Template, follow **[bootstrap/README.md](bootstrap/README.md)** or execute `@bootstrap/onboarding-prompt.md`.
