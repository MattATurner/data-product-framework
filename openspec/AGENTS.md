# How agents work in this repository

## Golden rules

1. **Never write a BRD as an engineer.** Use `skills/author-brd`, which interviews the
   business using the rubric. If an answer is unknown, record a `[NEEDS-DECISION: id]`
   marker — do not invent it.
2. **Never put modelling vocabulary in a BRD.** No grain, SCD, dimension, surrogate key,
   partition or BigQuery in a document a business SME owns.
3. **Derive, then confirm.** Modelling decisions live in the TDD and are played back to
   the business as `semantics.md` in their language.
4. **Cite requirement IDs.** Every TDD decision and manifest element names the BRD
   requirement (or platform capability) it satisfies. Unjustified design fails G1.
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

Skills declare their tier in front-matter (`metadata.dpf.tool_tier`). `dpf lint` fails a
skill sitting at tier 4–5 when the registry shows a tier 1–3 option covering one of its
`needs`, and fails bespoke code under `examples/` or `products/` that lacks a
`# dpf: skill=<id> tier=<n> adr=<ADR>` marker naming a real skill and an existing ADR.

## Workflow

```
propose -> BRD -> G0 -> TDD + semantics.md + sign-off -> G1 -> compose -> G2
        -> generate -> G3 -> deploy + record evidence -> G4 -> monitor -> (breach) -> new change
```

| Gate | Passes when | Command |
|---|---|---|
| G0 | the BRD answers the rubric, is approved and uses no modelling vocabulary | `dpf brd validate <product>` |
| G1 | the TDD and manifest resolve every requirement; the sign-off matches the semantic digest | `dpf check <product> --gate G1` |
| G2 | every stage composes from skills and adapters; every scenario (AX) maps to a test (AT) | `dpf check <product> --gate G2` |
| G3 | artefacts generate deterministically, match the golden copy, and every requirement traces to an artefact and a test | `dpf check <product> --gate G3` |
| G4 | every test has passing evidence for the **current** build digest | `dpf check <product> --gate G4` |

Gates are cumulative: `--gate G3` runs G0 to G3. Work happens as an OpenSpec change under
`openspec/changes/<id>/` (schema `data-product`), carrying delta specs against `brd/`
and/or `tdd/`. A TDD-only change needs no business re-approval.

`dpf monitor <product> --open-change` turns a breach of the observability policy into a
change with `skip_specs: true`. Remove `skip_specs` if the fix needs a spec change.

## Never fabricate evidence

Evidence files under `evidence/<product>/` record real runs against a deployed build
(`dpf test run --live`) or real human attestations (`dpf test attest`). Never write one by
hand, never copy one to a new build digest, and never weaken a check to make G4 pass. A
failing G4 is the correct state for a product that has not been run.

## When you are unsure

Ask, or record a `[NEEDS-DECISION]`. A recorded gap is cheap; an invented business rule
is expensive and hard to find later.
