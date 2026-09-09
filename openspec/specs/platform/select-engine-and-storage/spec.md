# Select Engine And Storage Specification

## Purpose

Choose the transform engine and storage format per layer, independently of methodology.

### Requirement: Neither is mandated

#### Scenario: Customer already uses dbt
- WHEN a customer is invested in dbt
- THEN dbt SHALL be selectable as the engine
- AND methodology packs SHALL require no change.

#### Scenario: Data must remain as files
- WHEN data must stay in GCS as Parquet, or must not move from another cloud
- THEN the corresponding storage option SHALL be selectable per layer.

### Requirement: Packs emit models, adapters emit artefacts

#### Scenario: Separation of concerns
- WHEN a methodology pack generates output
- THEN it SHALL emit a `semantic-model.v1` and SHALL NOT emit engine-specific artefacts
- AND the engine adapter SHALL NOT make modelling decisions.

### Requirement: Compatibility is declared, not assumed

#### Scenario: Streaming a history-bearing model
- WHEN a role requiring durable history is paired with a streaming engine
- AND the pack does not declare a streaming variant for that role
- THEN validation SHALL fail.

### Requirement: Materialisation is an explicit decision

#### Scenario: Choosing view versus materialised output
- WHEN a consumption model is defined
- THEN the TDD SHALL record view, materialized view, table or incremental table
- AND the choice SHALL cite the BRD freshness and volume answers.
