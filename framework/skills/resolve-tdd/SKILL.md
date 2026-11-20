---
name: resolve-tdd
description: 'Derive the technical design from an approved BRD: methodology per layer, grain, history,
  capture, engine, storage, quality, protection and service levels, with a source feasibility pass. Produces
  the narrative-and-visual TDD v2 (with co-located diagrams and normative appendices), playback.md and product.yaml.'
metadata:
  dpf:
    skill_id: resolve-tdd
    stage: design
    scope: product
    implements: select-methodology
    consumes:
    - brd.v1
    produces:
    - product-manifest.v1
    tool_tier: 4
    tool: dpf-local
    inspection_tool: mcp-toolbox-databases
    needs:
    - spec_validation
    - traceability
    gate: G1
---

# Resolve a BRD into a TDD (G1)

Roughly two thirds is mechanical; the rest is engineering judgement and gets an ADR. The
resulting Technical Design Document (`tdd/spec.md`) is written for two audiences in one
file: plain-English architecture, modular breakdown, data flow, entity model, and optional
dashboard mockups up front (Sections 1–8), backed by machine-verifiable technical decisions
and physical reference tables in Appendices A–D.

## Steps

1. Ask the user for the target **GCP project ID** (`deployment.gcp_project`) and **region**
   (`deployment.region`) where the product's assets will be deployed (never copy an example
   placeholder such as `data-product-framework` or `example-dpf-dev` for a real product).

2. Run `dpf tdd resolve <product>`. Review the rubric derivations (`registry/brd-rubric.yaml`)
   and the methodology recommendation driven by BRD signals.

3. Select methodology per layer (default `direct`), then engine and storage. Record any
   departure from `registry/platform-defaults.yaml` in an ADR listed in `product.yaml`.

4. Feasibility pass: inspect the real source with the MCP server named in the source
   registry (usually tier 2 `mcp-toolbox-databases`). Confirm keys, change timestamps,
   history retention, and reachability.

5. Author `products/<product>/product.yaml` (contract `product-manifest.v1`): every element
   cites `brd_requirement_id` or the platform capability it `implements`.

6. Generate the co-located visual views under `products/<product>/specs/tdd/assets/` (using
   the workspace's diagramming skills where available, verifying zero overlaps before embedding):
   - `assets/architecture.svg` — Solution & platform architecture diagram (services, layers,
     network boundaries, and cross-cutting governance).
   - `assets/functional-hierarchy.svg` — Chronological Functional Hierarchy Diagram (FHD)
     decomposing modular capabilities and atomic single-writer persistence units.
   - `assets/data-flow.svg` — Runtime data flow diagram tracing capture, deduplication,
     blocking/quarantine quality gates, history/restatement windows, and publishing ports.
   - `assets/entity-model.svg` — Crow's Foot Entity-Relationship diagram showing tables vs.
     rounded views, keys (`PK`/`SK`/`NK`/`FK`/`*`), policy-tagged PII columns, SCD2 tracked
     attributes, and BigQuery grain/partition/cluster footers.
   - `assets/dashboard-mockup.png` — *(When BI / dashboards are declared in `semantic_layer.dashboards`)*
     Annotated low-clutter dashboard wireframe aligned with the declared filters, KPIs, and
     zero-baseline charts.

7. Write `products/<product>/specs/tdd/spec.md` following `framework/templates/design/tdd-spec.md`:
   - `## Purpose` with `**TDD:**`, `**Satisfies:**`, `**Version:**`, `**Owner:**` metadata
     and a Document Control table.
   - Sections 1–8 in plain English embedding the visual assets from `assets/`.
   - `## Appendix A — Normative Technical Requirements` containing one `### Requirement:`
     per decision with `**Decision:** D-n · **Satisfies:** R-..` (plus `**Model:**` and
     `**Grain:**` for every consumption model, `**Layer:**` + `**Methodology:**` for layer
     methodology decisions, and `**ADR:**` for departures), normative `SHALL`/`MUST`
     statements, and `#### Scenario:` (`WHEN`/`THEN`) blocks.
   - Appendices B–D covering Decision Coverage & Derivations, Physical Implementation
     Reference, and ADRs / Source Feasibility Evidence.

8. Write `tdd/playback.md` (or `tdd/semantics.md`): the concise, jargon-free business
   playback page for business owner sign-off.

9. Run Pass G1 of `.agents/skills/goldfish-verify` in a fresh, zero-context subagent given
   only `products/<product>/product.yaml` and `products/<product>/sql/*.sql` (never `brd/` or
   `tdd/`), and reconcile `generated/<product>/goldfish-playback.md` against `tdd/playback.md`
   (`tdd/semantics.md`) and `brd/brd.yaml` before asking for sign-off.

10. Get the business owner to sign: `dpf signoff <product> --by <name> --role business_owner`.

11. Run `dpf check <product> --gate G1` and confirm zero failures (including all visual asset
    links) and zero unintended structural warnings.

## Feasibility failures are business issues

If the source cannot meet a requirement, raise it against the BRD in business language and
bump the BRD version when the business accepts a change. Never degrade it silently.
