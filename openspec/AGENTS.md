# How agents work in this repository

## Golden rules

1. **Never write a BRD as an engineer.** Use `skills/author-brd`, which interviews the
   business using the rubric. If an answer is unknown, record a `[NEEDS-DECISION: id]`
   marker — do not invent it.
2. **Never put modelling vocabulary in a BRD.** No grain, SCD, dimension, surrogate key,
   partition or BigQuery in a document a business SME owns.
3. **Derive, then confirm.** Modelling decisions live in the TDD and are played back to
   the business as `semantics.md` in their language.
4. **Cite requirement IDs.** Every TDD decision names the BRD requirement it satisfies.
   Unjustified design fails `dpf trace`.
5. **Prefer MCP and existing agents.** Before writing integration code, consult
   `registry/mcp_servers.yaml` and the tier order in
   `openspec/specs/platform/tool-selection/spec.md`.

## Tool selection order (enforced)

| Tier | Use | Example |
|---|---|---|
| 1 | Managed remote MCP server | BigQuery MCP; Knowledge Catalog MCP |
| 2 | Self-hosted MCP server | MCP Toolbox for Databases (Oracle, Postgres, Spanner, ...) |
| 3 | Existing managed agent or API | Conversational Analytics API; Document AI; Datastream API |
| 4 | Official SDK / CLI / Terraform provider | `google-cloud-bigquery`, `bq`, `gcloud`, Terraform |
| 5 | Bespoke code | **Requires an ADR** explaining why tiers 1–4 do not work |

Skills declare their tier in front-matter. `dpf lint` fails a skill sitting at tier 4–5
when the registry shows a tier 1–3 option covering the same capability.

## Workflow

```
propose  ->  author/refine BRD  ->  G0  ->  resolve TDD + semantics  ->  G1
         ->  compose skills  ->  generate artefacts  ->  G2/G3  ->  deploy  ->  G4
```

Work happens as an OpenSpec change under `openspec/changes/<id>/`, carrying delta specs
against `brd/` and/or `tdd/`. A TDD-only change needs no business re-approval.

## When you are unsure

Ask, or record a `[NEEDS-DECISION]`. A recorded gap is cheap; an invented business rule
is expensive and hard to find later.
