# Tool Selection Specification

## Purpose

Ensure the framework reuses existing MCP servers, agents and managed APIs instead of
writing bespoke integration code, and that any departure from that is deliberate and
recorded.

### Requirement: Tiered tool resolution

Skills SHALL select their integration mechanism in tier order, preferring the lowest
tier number that can perform the operation.

| Tier | Mechanism |
|---|---|
| 1 | Managed remote MCP server |
| 2 | Self-hosted MCP server |
| 3 | Existing managed agent or API |
| 4 | Official SDK, CLI or Terraform provider |
| 5 | Bespoke code |

#### Scenario: A managed MCP server exists
- WHEN a skill needs an operation covered by a tier 1 entry in `registry/mcp_servers.yaml`
- THEN the skill SHALL use that MCP server
- AND the skill front-matter SHALL declare `tool_tier: 1` and the server id.

#### Scenario: No MCP server exists for the capability
- WHEN no registry entry covers the operation
- AND the capability appears under `no_mcp_option_yet`
- THEN the skill MAY use tier 4 without an ADR
- AND SHALL declare the tier in front-matter.

#### Scenario: Bespoke code is proposed
- WHEN a skill declares `tool_tier: 5`
- THEN an ADR SHALL exist explaining why tiers 1-4 cannot serve the need
- AND validation SHALL fail if that ADR is absent.

#### Scenario: A skill under-uses an available server
- WHEN a skill declares tier 4 or 5
- AND a tier 1-3 registry entry covers the same capability
- THEN `dpf lint` SHALL fail with the covering server named.

### Requirement: The registry is authoritative and reviewable

`registry/mcp_servers.yaml` SHALL list every known MCP server and agent surface with its
tier, coverage, IAM roles and documentation link.

#### Scenario: New platform capability ships
- WHEN a new MCP server becomes available for a capability listed under `no_mcp_option_yet`
- THEN the registry SHALL be updated
- AND skills sitting at tier 4 for that capability SHALL be re-reviewed.

#### Scenario: Preview or limited-support surface
- WHEN a registry entry is preview or offered with limited support
- THEN that SHALL be recorded in the entry's notes
- AND a skill depending on it for a blocking gate SHALL declare a fallback.

### Requirement: Agent-first for analytical access

Where a managed agent already provides a capability, the framework SHALL NOT build a
competing implementation.

#### Scenario: Natural-language access to a published product
- WHEN consumers need natural-language querying over a published data product
- THEN the Conversational Analytics API SHALL be used
- AND a bespoke NL2SQL layer SHALL NOT be generated.
