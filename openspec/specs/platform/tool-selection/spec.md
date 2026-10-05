# Tool Selection Specification

## Purpose

Ensure the framework reuses existing MCP servers, agents and managed APIs instead of writing
bespoke integration code, and that any departure from that is deliberate and recorded.

## Requirements

### Requirement: Tiered tool resolution
Skills SHALL select their integration mechanism in tier order — managed remote MCP server (1),
self-hosted MCP server (2), managed agent or API (3), official SDK, CLI or provider (4), bespoke
code (5) — and SHALL declare the tier of the tool that executes them.

#### Scenario: A managed MCP server exists
- **WHEN** a skill needs a capability covered by a tier 1 registry entry
- **THEN** the skill SHALL use that server and declare `tool_tier: 1`

#### Scenario: A skill under-uses an available server
- **WHEN** a skill declares tier 4 or 5
- **AND** a tier 1 to 3 registry entry covers a capability the skill needs
- **THEN** lint SHALL fail and name the covering server

### Requirement: Declared tiers match the registry
A skill's declared tier SHALL equal the registered tier of the tool it names.

#### Scenario: Inflated tier
- **WHEN** a skill claims tier 1 but its executing tool is registered at tier 4
- **THEN** lint SHALL fail

### Requirement: Bespoke code is marked and justified
Every hand-written integration program SHALL carry a marker naming its skill, tier and ADR, and
the ADR SHALL exist.

#### Scenario: Unmarked integration code
- **WHEN** a program imports a cloud or database client without a marker
- **THEN** lint SHALL fail

#### Scenario: Tier 5 without an ADR
- **WHEN** a skill or program declares tier 5 and its ADR does not exist
- **THEN** lint SHALL fail

### Requirement: The registry is authoritative and reviewable
The registry SHALL list every known MCP server, agent surface and tier 4 tool with its tier,
coverage and documentation, and preview surfaces SHALL be marked.

#### Scenario: New platform capability ships
- **WHEN** a new MCP server becomes available for a capability listed as having no MCP option
- **THEN** the registry SHALL be updated
- **AND** skills sitting at tier 4 for that capability SHALL be re-reviewed

### Requirement: Agent-first for analytical access
Where a registered managed agent provides a capability, the framework SHALL NOT build a competing
implementation.

#### Scenario: Natural-language access to a published product
- **WHEN** consumers need natural-language querying over a published data product
- **THEN** the registered tier 3 analytical agent SHALL be used
- **AND** a bespoke text-to-query layer SHALL NOT be generated
