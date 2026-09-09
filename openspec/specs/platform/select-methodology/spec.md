# Select Methodology Specification

## Purpose

Choose a modelling methodology per layer, or none at all, and record why.

### Requirement: Methodology is optional

The framework SHALL support products with no formal modelling methodology.

#### Scenario: Simple single-source product
- WHEN a product has one source, one consumer group, needs only current state and has
  no cross-domain reconciliation requirement
- THEN `direct` SHALL be recommended
- AND a heavyweight methodology SHALL NOT be imposed.

#### Scenario: Unjustified heavyweight methodology
- WHEN a methodology is selected without a BRD signal justifying it
- THEN design review SHALL flag it as a defect
- BECAUSE a methodology is a cost paid for a benefit.

### Requirement: Methodology is a TDD decision

#### Scenario: BRD names a methodology
- WHEN a BRD names a modelling methodology
- THEN validation SHALL fail
- BECAUSE methodology is meaningless to the business author.

### Requirement: Selection is per layer

#### Scenario: Mixed methodologies
- WHEN silver and gold require different shapes
- THEN each layer SHALL declare its own methodology
- AND the handoff SHALL remain a `semantic-model.v1` contract.

### Requirement: Deviation is recorded

#### Scenario: Departing from the domain default
- WHEN the selected methodology differs from `registry/platform-defaults.yaml`
- THEN an ADR SHALL be recorded
- AND the engineering lead SHALL approve at G1.
