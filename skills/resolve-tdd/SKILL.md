---
skill_id: resolve-tdd
implements: traceability
consumes: brd.yaml
produces: tdd/spec.md, semantics.md, product.yaml
tool_tier: 2
tool: mcp-toolbox-databases
gate: G1
---

# Resolve a BRD into a TDD

Derive the design. Roughly two thirds is mechanical; the rest is engineering judgement
and gets an ADR.

## Steps

1. **Derive** grain, history semantics, additivity, restatement window and retention from
   the BRD answers (see the derivation table in the plan).
2. **Select** methodology per layer (default `direct`), then engine and storage per layer.
   Record any deviation from `registry/platform-defaults.yaml` as an ADR.
3. **Check compatibility**: the pack must declare support for each role/engine pairing.
4. **Feasibility pass** — inspect the real source using an MCP server from
   `registry/mcp_servers.yaml` (tier 2 `mcp-toolbox-databases` for most relational
   sources). Confirm the source can actually satisfy each requirement.
5. **Write `tdd/spec.md`** with `satisfies: <brd_id>@<version>`. Every requirement cites
   a BRD requirement id.
6. **Generate `semantics.md`** — the derived model restated in business language, for
   signature.
7. **Emit `product.yaml`** — the resolved manifest.

## Feasibility failures are business issues

When the source cannot meet a requirement — segment history was never captured, the
natural key is not unique, there is no reliable change timestamp — raise it as a
**business-language issue against the BRD**. Do not silently degrade the requirement.

## Must

- Cite a BRD requirement id on every decision. Uncited decisions fail `dpf trace`.
- Never let the derived grain diverge from what `semantics.md` states.
