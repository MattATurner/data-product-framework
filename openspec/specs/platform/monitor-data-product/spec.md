# Monitor Data Product Specification

## Purpose

Keep a published product inside its service levels: machine-readable freshness against a
business calendar, volume bounds, schema-drift alerts and quality scans, with breaches feeding
back into the change process.

## Requirements

### Requirement: Service levels are machine-readable
Every freshness need in the BRD SHALL be expressed as a maximum staleness and a business
calendar that tooling can evaluate.

#### Scenario: Free-text freshness
- **WHEN** a manifest states freshness only as prose
- **THEN** validation SHALL fail

### Requirement: Freshness is evaluated inside the business calendar
A freshness breach SHALL be raised only when, inside the business calendar, the time since the
last successful build exceeds the maximum staleness.

#### Scenario: Weekend silence
- **WHEN** no build runs outside the business calendar
- **THEN** no freshness breach SHALL be raised

#### Scenario: Stale during the working day
- **WHEN** inside the calendar the last build is older than the maximum staleness
- **THEN** a breach SHALL be raised for the product and model

### Requirement: Volume is bounded
Daily volume SHALL be compared with the expected volume and tolerance derived from the BRD.

#### Scenario: Volume collapse
- **WHEN** a day's rows fall below the lower bound
- **THEN** a breach SHALL be raised

### Requirement: Monitoring is generated with the product
Quality scans, freshness checks and alert policies SHALL be generated from the observability
policy together with the other artefacts.

#### Scenario: Deploying a product
- **WHEN** a product is generated
- **THEN** its scans, checks and alert routing SHALL be among the generated artefacts

### Requirement: Breaches open a change
A confirmed breach SHALL be able to open a change proposal that records the evidence and asks
whether the requirement or the design must change.

#### Scenario: Repeated freshness breach
- **WHEN** a breach is confirmed
- **THEN** a change proposal SHALL be created under `openspec/changes/` with the evidence attached
