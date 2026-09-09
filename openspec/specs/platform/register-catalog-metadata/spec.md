# Register Catalog Metadata Specification

## Purpose

Make a data product discoverable, understood and governed before it can be published.

### Requirement: Registration is a gate, not a courtesy

#### Scenario: Missing required aspect
- WHEN a product lacks a required catalog aspect
- THEN it SHALL NOT reach `published` status.

### Requirement: Required metadata

#### Scenario: Registering a product
- WHEN a product is registered
- THEN owner, domain, classification, service levels, grain, refresh cadence, BRD link,
  TDD link and signed semantics link SHALL be present.

### Requirement: Provisional products are labelled

#### Scenario: Live assumptions
- WHEN a product carries unresolved BRD assumptions
- THEN it SHALL be registered as `provisional`
- AND the assumptions SHALL be visible to consumers as an aspect.

### Requirement: Prefer the catalog MCP server

#### Scenario: Registration mechanism
- WHEN registering catalog metadata
- THEN the tier 1 Knowledge Catalog MCP server SHALL be used where available
- AND a lower tier SHALL be recorded with its reason.
