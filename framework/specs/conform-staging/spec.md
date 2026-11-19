# Conform Staging Specification

## Purpose

Turn raw rows into typed, deduplicated, house-standard rows without applying any modelling
methodology. Every product has a staging layer.

## Requirements

### Requirement: Deterministic re-run
Rebuilding staging from unchanged raw data SHALL produce identical output.

#### Scenario: Re-running over the same raw partitions
- **WHEN** staging is rebuilt from unchanged raw data
- **THEN** the output SHALL be identical

### Requirement: Deduplication is explicit
Staging SHALL keep exactly one row per natural key using the declared ordering, and SHALL assert
uniqueness on the natural key.

#### Scenario: Duplicate natural keys
- **WHEN** more than one row shares a natural key
- **THEN** the declared ordering SHALL select exactly one
- **AND** the uniqueness assertion SHALL pass

### Requirement: Rejects are quarantined, never dropped
Rows failing a fitness rule SHALL be routed to a reject relation with a reason, and SHALL NOT
silently disappear.

#### Scenario: Unusable row
- **WHEN** a row fails the BRD's fitness definition
- **THEN** it SHALL appear in the reject relation with the failing rule and reason

### Requirement: Rejects block publication when the business says stop
When the BRD says bad data must stop publication, a blocking check on the reject relation SHALL
be a dependency of every published output.

#### Scenario: A reject exists
- **WHEN** the reject relation contains rows
- **THEN** the build SHALL fail before any output port is refreshed
- **AND** the team SHALL be alerted
