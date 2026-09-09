---
skill_id: register-knowledge-catalog
implements: register-catalog-metadata
consumes: data-product.v1
produces: catalog-registration.v1
tool_tier: 1
tool: knowledge-catalog-mcp
gcp: [Knowledge Catalog]
---

# Register in Knowledge Catalog

**Use the Knowledge Catalog MCP server (tier 1).** Fall back to the Dataplex API only if
it is unavailable, and record the reason on the contract's `registered_via`.

> The remote MCP server is offered with limited support at time of writing. Because this
> skill sits on a blocking gate, declare the API fallback in the TDD.

## Required aspects

owner, domain, classification, service levels, **grain**, refresh cadence, BRD link,
TDD link, signed semantics link, live assumptions.

## Steps

1. Create or update the catalog entry for each output port.
2. Attach aspects; bind glossary terms from `registry/glossary.yaml`.
3. Record lineage edges from the composed DAG.
4. Bind the quality scan.
5. Set status: `provisional` while assumptions are live, otherwise `published`.

## Must

- Block publication when a required aspect is missing.
- Never register a product as `published` before G4 acceptance.
