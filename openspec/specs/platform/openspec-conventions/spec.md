# OpenSpec Conventions Specification

## Purpose

House rules for writing specifications in this repository.

### Requirement: Requirement and scenario structure

Every specification SHALL use `### Requirement: ...` followed by at least one
`#### Scenario: ...`.

#### Scenario: Requirement without a scenario
- WHEN a requirement has no scenario
- THEN validation SHALL fail
- BECAUSE a requirement with no verifiable scenario cannot be tested.

### Requirement: Behaviour, not implementation

Specifications SHALL describe externally observable behaviour and SHALL NOT name
concrete services, libraries or SQL constructs.

#### Scenario: Implementation leaking into a capability spec
- WHEN a platform capability spec names a specific product or statement type
- THEN validation SHALL warn
- AND the detail SHALL move to a skill, an engine adapter or an ADR.

### Requirement: Three spec families

Specifications SHALL be one of: platform capability, product BRD, or product TDD.

#### Scenario: Modelling vocabulary in a BRD
- WHEN a product BRD contains grain, SCD, dimension, surrogate key, partition or a
  warehouse product name
- THEN validation SHALL fail
- BECAUSE the BRD is authored by a business SME.
