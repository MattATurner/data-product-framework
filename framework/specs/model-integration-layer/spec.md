# Model Integration Layer Specification

## Purpose

Methodology-neutral contract for the silver layer. The active pack supplies the legal roles and
the modelling rules; this capability fixes what is true regardless of pack.

## Requirements

### Requirement: Grain is declared, approved and asserted
Every silver model SHALL declare a grain statement and grain columns equal to the grain approved
in the TDD, and a uniqueness assertion SHALL be generated from those columns.

#### Scenario: Grain diverges from the TDD
- **WHEN** a manifest grain differs from the grain declared in the approved TDD
- **THEN** G1 SHALL fail

### Requirement: History semantics follow the business answer
A model satisfying a requirement whose history answer keeps past figures as they were SHALL
declare point-in-time history.

#### Scenario: Point-in-time attribution required
- **WHEN** the BRD says past figures keep the value that applied at the time
- **THEN** every model satisfying that requirement SHALL be point-in-time
- **AND** current-state-only output SHALL be rejected

### Requirement: Unknown members
A reference that cannot be resolved at build time SHALL resolve to an explicit unknown member.

#### Scenario: Unresolvable reference
- **WHEN** a referenced entity cannot be resolved
- **THEN** the reference SHALL resolve to the unknown member
- **AND** SHALL NOT be null and SHALL NOT drop the row

### Requirement: Conformed structures match the registry
A model declared as conformed SHALL match the registered grain, key and owning domain.

#### Scenario: Conformance conflict
- **WHEN** a product declares a conformed structure at a different grain or key
- **THEN** G1 SHALL fail and name the owning domain
