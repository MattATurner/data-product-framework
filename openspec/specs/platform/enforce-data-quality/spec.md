# Enforce Data Quality Specification

## Purpose

Derive quality rules from the BRD's fitness answers and bind them to the publication gate so a
failure actually stops publication.

## Requirements

### Requirement: Rules come from the BRD
Every quality rule SHALL cite the BRD requirement it enforces, and every fitness answer SHALL be
enforced by at least one rule.

#### Scenario: Fitness answer without a rule
- **WHEN** the BRD states what makes a row unusable and no rule cites that requirement
- **THEN** G1 SHALL fail

### Requirement: Stop means block
When the BRD says bad data must stop publication, the gate behaviour and every rule deriving
from that answer SHALL be blocking.

#### Scenario: Warning where the business said stop
- **WHEN** a fitness-derived rule is declared with warning severity
- **THEN** G1 SHALL fail

### Requirement: Every model carries a grain rule
Every model SHALL carry a blocking uniqueness rule on its declared grain columns.

#### Scenario: Duplicates at the declared grain
- **WHEN** duplicate rows exist at the declared grain
- **THEN** the build SHALL fail rather than warn
