# Conform Staging Specification

## Purpose

Turn raw rows into typed, deduplicated, house-standard rows without applying any
modelling methodology.

### Requirement: Deterministic re-run

#### Scenario: Re-running over the same raw partitions
- WHEN staging is rebuilt from unchanged raw data
- THEN the output SHALL be identical.

### Requirement: Deduplication is explicit

#### Scenario: Duplicate natural keys
- WHEN more than one row shares a natural key
- THEN the declared dedupe strategy SHALL select exactly one
- AND the staging model SHALL assert uniqueness on the natural key.

### Requirement: Rejects are quarantined, never dropped

#### Scenario: Unusable row
- WHEN a row fails the BRD's fitness definition
- THEN it SHALL be written to the reject table with a reason
- AND SHALL NOT silently disappear.
