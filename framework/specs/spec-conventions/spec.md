# Specification Conventions Specification

## Purpose

House rules for writing specifications in this repository, so that every spec is readable by
people, parseable and validated by `dpf`, and testable through its scenarios.

## Requirements

### Requirement: Specification structure

Every specification SHALL contain a `## Purpose` section and a `## Requirements` section. Each
`### Requirement:` SHALL state one behaviour using SHALL or MUST and SHALL have at least one
`#### Scenario:` written with bold WHEN and THEN steps.

#### Scenario: Requirement without a scenario

- **WHEN** a requirement has no scenario
- **THEN** validation SHALL fail
- **BECAUSE** a requirement with no verifiable scenario cannot be tested

#### Scenario: Requirement without a normative statement

- **WHEN** a requirement body contains neither SHALL nor MUST
- **THEN** validation SHALL fail

### Requirement: Identifiers live in metadata lines

Requirement and scenario identifiers SHALL be written on a metadata line directly below the
heading (for example `**ID:** R-4` or `**Decision:** D-3 · **Satisfies:** R-2`) and SHALL NOT be
part of the heading text.

#### Scenario: Identifier in a heading

- **WHEN** a requirement heading carries an identifier such as `[R-4]`
- **THEN** validation SHALL fail
- **BECAUSE** requirement titles must stay human-readable and stable across diffs

### Requirement: Co-located product specs and kebab-case capability specs

Platform capability specifications SHALL live under `framework/specs/<capability>/spec.md` with
kebab-case capability folder names, and product specifications SHALL live beside each product's
manifest at `products/<product>/specs/{brd,tdd}/` (or `examples/<product>/specs/{brd,tdd}/`).

#### Scenario: Non-kebab-case platform capability folder

- **WHEN** a platform capability spec lives under a folder containing underscores or uppercase letters
- **THEN** validation SHALL fail and name the kebab-case path to use

### Requirement: Behaviour, not implementation

Platform capability specifications SHALL describe externally observable behaviour and SHALL
NOT name concrete cloud services, libraries or SQL constructs. Mechanisms belong in skills,
engine adapters, registry entries or ADRs.

#### Scenario: Implementation leaking into a capability spec

- **WHEN** a platform capability spec names a specific product or service
- **THEN** validation SHALL warn
- **AND** the detail SHALL move to a skill, an engine adapter, the registry or an ADR

### Requirement: Three spec families

Specifications SHALL be one of: platform capability, product BRD, or product TDD.

#### Scenario: Modelling vocabulary in a BRD

- **WHEN** a product BRD contains modelling vocabulary or a warehouse product name
- **THEN** validation SHALL fail
- **BECAUSE** the BRD is authored by a business SME
