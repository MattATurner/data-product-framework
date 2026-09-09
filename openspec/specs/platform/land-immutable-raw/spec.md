# Land Immutable Raw Specification

## Purpose

Land source data immutably so that everything downstream can be rebuilt.

### Requirement: Raw is append-only and source-shaped

#### Scenario: Attempted mutation
- WHEN a process attempts to update or delete a landed raw row
- THEN the operation SHALL be rejected.

#### Scenario: Lineage columns
- WHEN a batch is landed
- THEN every row SHALL carry ingest timestamp, batch id, source system and, for change
  data, the operation type.

### Requirement: Every batch has a manifest

#### Scenario: Batch completes
- WHEN a batch lands
- THEN a `landing-manifest.v1` SHALL be emitted with row count and watermark bounds
- AND a batch without a manifest SHALL NOT be consumed downstream.

### Requirement: Schema drift is classified

#### Scenario: Additive drift
- WHEN a new nullable column appears at source
- THEN the batch SHALL land successfully
- AND the schema fingerprint SHALL be updated.

#### Scenario: Breaking drift
- WHEN a column is removed or changes type incompatibly
- THEN the batch SHALL be quarantined
- AND an alert SHALL be raised naming the entity and the change.
