# Register Catalog Metadata Specification

## Purpose

Make a data product discoverable, understood and governed before it can be published.

## Requirements

### Requirement: Registration is a gate, not a courtesy
A product lacking any required catalog aspect SHALL NOT reach `published` status.

#### Scenario: Missing required aspect
- **WHEN** a product lacks a required catalog aspect
- **THEN** it SHALL NOT reach `published` status

### Requirement: Required metadata
Registration SHALL carry owner, domain, classification, service levels, grain, refresh cadence,
status, live assumptions, BRD link, TDD link and signed semantics link.

#### Scenario: Registering a product
- **WHEN** a product is registered
- **THEN** every required aspect SHALL be present and validate against the registration contract

### Requirement: Provisional products are labelled
A product carrying unresolved BRD assumptions SHALL be registered as `provisional`.

#### Scenario: Live assumptions
- **WHEN** a product carries unresolved BRD assumptions
- **THEN** it SHALL be registered as `provisional`
- **AND** the assumptions SHALL be visible to consumers as an aspect

### Requirement: Prefer the registered catalog MCP server
Registration SHALL use the tier 1 catalog MCP server listed in the registry where available, and
any fallback SHALL be declared with its reason.

#### Scenario: Registration mechanism
- **WHEN** registering catalog metadata
- **THEN** the tier 1 catalog MCP server SHALL be used where available
- **AND** a lower tier SHALL be recorded with its reason
