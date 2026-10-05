# Test Data Product Specification

## Purpose

Make the business acceptance scenarios, the declared grain and the quality policy executable,
and record evidence that proves a build before it is published (gate G4).

## Requirements

### Requirement: Tests are generated from the specification
The test specification SHALL be generated from the declared grain of every model, the quality
policy, the pack's integrity rules and the acceptance mapping, and SHALL NOT be hand-maintained.

#### Scenario: New model added
- **WHEN** a model is added to the manifest
- **THEN** its grain test SHALL appear in the next generated test specification

### Requirement: Every acceptance scenario is verified
Every acceptance scenario SHALL be verified by an automated test, a static check or a recorded
human attestation.

#### Scenario: Reconciliation that needs a person
- **WHEN** a scenario can only be confirmed by another team
- **THEN** it SHALL be verified by an attestation naming the attesting role

### Requirement: Evidence is bound to the build
Test evidence SHALL record the build digest it was produced against, and evidence for another
digest SHALL NOT count at G4.

#### Scenario: Stale evidence
- **WHEN** evidence was recorded for a previous build
- **THEN** G4 SHALL report it stale and fail

### Requirement: Acceptance fixtures stay out of production
Tests that assume fixture data SHALL be tagged so that production schedules never run them.

#### Scenario: Production run
- **WHEN** the production schedule runs
- **THEN** fixture-dependent acceptance tests SHALL be excluded
