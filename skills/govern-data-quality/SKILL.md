---
name: govern-data-quality
description: 'Turn the BRD fitness answers and declared grains into the quality policy: quarantine and
  blocking rules bound to the publication gate, plus scheduled Knowledge Catalog data quality scans. Use
  for every product.'
metadata:
  dpf:
    skill_id: govern-data-quality
    stage: govern
    scope: product
    implements: enforce-data-quality
    consumes:
    - product-manifest.v1
    produces:
    - quality-policy.v1
    tool_tier: 4
    tool: dpf-local
    needs:
    - artefact_generation
    gcp:
    - BigQuery
    - Knowledge Catalog
---

# Generate the quality policy

Rules come from the BRD's fitness answers, never invented here.

| BRD answer | Rule |
|---|---|
| "Unusable if no customer recorded" | `not_null` on the customer reference, `on_fail: quarantine`, severity block |
| "Unusable if quantity is negative" | `range` min 0, `on_fail: quarantine`, severity block |
| Declared grain | `GR-<model>` uniqueness, severity block (generated for every model) |
| "Stop and alert" | `gate_behaviour: block` |

`dpf generate` writes `quality-policy.json`, the reject gates and the data quality scans
listed in `observability.quality_scans`. G1 fails when the BRD says "stop" but no blocking
rule cites the fitness requirement.
