---
name: register-knowledge-catalog
description: Register each output port in Knowledge Catalog with required aspects (owner, domain, classification,
  grain, service levels, status), glossary terms, lineage and quality scans, using the managed MCP server.
metadata:
  dpf:
    skill_id: register-knowledge-catalog
    stage: register
    scope: product
    implements: register-catalog-metadata
    consumes:
    - data-product.v1
    produces:
    - catalog-registration.v1
    tool_tier: 1
    tool: knowledge-catalog-mcp
    needs:
    - catalog_entries
    - aspects
    - glossaries
    gcp:
    - Knowledge Catalog
---

# Register in Knowledge Catalog

Use the Knowledge Catalog MCP server (tier 1). Fall back to the API only if it is
unavailable, and record the fallback in `registered_via`.

## Inputs

`generated/<product>/catalog-registration.json` (contract `catalog-registration.v1`):
entry, required aspects, glossary terms, lineage edges, BRD/TDD/semantics links.

## Steps

1. Create or update the entry for each output port.
2. Attach the aspects; bind glossary terms to columns.
3. Record lineage edges from the composed DAG.
4. Link the data quality scan.
5. Set status `provisional` while assumptions are live, otherwise `published`.

## Must

- Block publication when a required aspect is missing.
- Never register a product as `published` before G4.
