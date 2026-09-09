# Model Integration Layer Specification

## Purpose

Methodology-neutral contract for the silver layer. The active pack supplies the legal
roles and the modelling rules; this capability fixes what is true regardless of pack.

### Requirement: Grain is declared and asserted

#### Scenario: Any modelled table or view
- WHEN a silver model is generated
- THEN it SHALL declare a grain statement and grain columns
- AND a uniqueness assertion SHALL be generated from those columns.

#### Scenario: Grain diverges from the TDD
- WHEN a manifest grain differs from the approved TDD grain checksum
- THEN the build SHALL fail.

#### Scenario: Data violates the declared grain
- WHEN duplicate rows exist at the declared grain
- THEN the build SHALL fail rather than warn.

### Requirement: History semantics are declared

#### Scenario: Point-in-time attribution required
- WHEN the TDD declares point-in-time history
- THEN the model SHALL preserve attribute state as at the event date
- AND current-state-only output SHALL be rejected.

### Requirement: Unknown members

#### Scenario: Unresolvable reference
- WHEN a referenced entity cannot be resolved at build time
- THEN the reference SHALL resolve to an explicit unknown member
- AND SHALL NOT be null and SHALL NOT drop the row.
