---
skill_id: assemble-data-product
implements: model-consumption-layer
consumes: semantic-model.v1
produces: data-product.v1
tool_tier: 4
tool: local
---

# Assemble the data product descriptor

Turn the gold semantic model plus the BRD and TDD metadata into a `data-product.v1`.

## Steps

1. Collect output ports, owner, domain, classification and service levels.
2. Carry the grain forward from the gold semantic model — it becomes a catalog aspect.
3. Set `semantics_signed` from the signature on `semantics.md`.
4. Copy live BRD assumptions. **Any assumption forces `status: provisional`.**
5. Apply semver: a breaking output-port or grain change needs a major bump.

## Must

- Refuse to mark `published` before G4 acceptance.
- Fail when `semantics_signed` is false.
