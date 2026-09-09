---
skill_id: govern-data-quality
implements: brd-completeness
consumes: semantic-model.v1
produces: quality-policy.v1
tool_tier: 1
tool: knowledge-catalog-mcp
gcp: [Knowledge Catalog data quality scans, Dataform assertions]
---

# Generate the quality policy

Rules come from the BRD's fitness answers — never invented here.

| BRD answer | Rule |
|---|---|
| "Unusable if no customer recorded" | `not_null` on the customer reference, severity block |
| "Unusable if quantity is negative" | `range` >= 0, severity block |
| Declared grain | `unique` on grain columns, severity block |
| Freshness target | `freshness` rule against the SLO |
| "Stop and alert" vs "flag it" | `gate_behaviour: block` vs `warn` |

## Must

- Cite the BRD requirement id on every rule.
- Bind blocking rules to the orchestration gate so a failure actually stops publication.
