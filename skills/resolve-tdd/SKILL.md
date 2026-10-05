---
name: resolve-tdd
description: 'Derive the technical design from an approved BRD: methodology per layer, grain, history,
  capture, engine, storage, quality, protection and service levels, with a source feasibility pass. Produces
  the TDD, semantics.md and product.yaml.'
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

Roughly two thirds is mechanical; the rest is engineering judgement and gets an ADR.

## Steps

1. `dpf tdd resolve <product>` prints the derivations (`registry/brd-rubric.yaml`) and the
   methodology recommendation from the BRD signals.
2. Select methodology per layer (default `direct`), then engine and storage. Record any
   departure from `registry/platform-defaults.yaml` in an ADR listed in `product.yaml`.
3. Feasibility pass: inspect the real source with the MCP server named in the source
   registry (usually tier 2 `mcp-toolbox-databases`). Confirm keys, change timestamps and
   reachability.
4. Write `tdd/spec.md`: one `### Requirement:` per decision with
   `**Decision:** D-n · **Satisfies:** R-..` (plus `**Model:**` and `**Grain:**` when the
   decision fixes a grain) and a verification scenario.
5. Write `tdd/semantics.md`: the design restated in business language, for signature.
6. Write `products/<product>/product.yaml` (contract `product-manifest.v1`): every element
   cites `brd_requirement_id` or the platform capability it `implements`.
7. Get the business owner to sign: `dpf signoff <product> --by <name> --role business_owner`.
8. `dpf check <product> --gate G1`.

## Feasibility failures are business issues

If the source cannot meet a requirement, raise it against the BRD in business language and
bump the BRD version when the business accepts a change. Never degrade it silently.
