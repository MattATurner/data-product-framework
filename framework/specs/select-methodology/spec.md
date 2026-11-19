# Select Methodology Specification

## Purpose

Choose a modelling methodology per layer, or none at all, and record why.

## Requirements

### Requirement: Methodology is optional
The framework SHALL support products with no formal modelling methodology, and `direct` SHALL be
the default.

#### Scenario: Simple single-source product
- **WHEN** a product has no cross-team agreement and no point-in-time history need
- **THEN** `direct` SHALL be recommended
- **AND** a heavyweight methodology SHALL NOT be imposed

### Requirement: Heavyweight methodology must be justified
A methodology other than the default SHALL be selected only when the BRD carries a signal that
justifies it, and the deviation SHALL be recorded in an ADR.

#### Scenario: Unjustified heavyweight methodology
- **WHEN** a heavyweight methodology is selected without a justifying BRD signal
- **THEN** G1 SHALL fail
- **BECAUSE** a methodology is a cost paid for a benefit

#### Scenario: Deviation without an ADR
- **WHEN** the selected methodology differs from the platform default and no ADR is listed
- **THEN** G1 SHALL fail

### Requirement: Methodology is a TDD decision
A BRD SHALL NOT name a modelling methodology.

#### Scenario: BRD names a methodology
- **WHEN** a BRD names a modelling methodology
- **THEN** validation SHALL fail

### Requirement: Selection is per layer
Each modelled layer SHALL declare its own methodology, and the handoff between layers SHALL be a
semantic model.

#### Scenario: Mixed methodologies
- **WHEN** silver and gold require different shapes
- **THEN** each layer SHALL declare its own methodology
