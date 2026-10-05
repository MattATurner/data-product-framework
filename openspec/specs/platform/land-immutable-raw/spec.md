# Land Immutable Raw Specification

## Purpose

Land source data immutably so that everything downstream can be rebuilt.

## Requirements

### Requirement: Raw is append-only and source-shaped
Landed raw rows SHALL never be updated or deleted, and every row SHALL carry lineage columns.

#### Scenario: Attempted mutation
- **WHEN** a process attempts to update or delete a landed raw row
- **THEN** the operation SHALL be rejected

#### Scenario: Lineage columns
- **WHEN** a batch is landed
- **THEN** every row SHALL carry ingest timestamp, batch id, source system, operation type and a natural-key hash

### Requirement: Every batch has a persisted manifest
Every landed batch SHALL persist a landing manifest with row count, watermark bounds and schema
fingerprint, and a batch without a persisted manifest SHALL NOT be consumed.

#### Scenario: Batch completes
- **WHEN** a batch lands
- **THEN** its manifest SHALL be persisted in the control area in the same unit of work

### Requirement: Schema drift is classified
Each batch's schema SHALL be compared with the last accepted schema and classified as none,
additive or breaking.

#### Scenario: Additive drift
- **WHEN** a new column appears at source
- **THEN** the batch SHALL land and the accepted schema SHALL be updated

#### Scenario: Breaking drift
- **WHEN** a column is removed or changes type incompatibly
- **THEN** the batch SHALL be quarantined, the watermark SHALL NOT advance
- **AND** a structured alert SHALL be raised naming the entity and the change
