# Select Engine And Storage Specification

## Purpose

Choose the transform engine and storage format per layer, independently of methodology.

## Requirements

### Requirement: Neither is mandated
The engine and the storage format SHALL be selectable per layer without changing methodology
packs.

#### Scenario: Customer already uses a different transform engine
- **WHEN** a customer is invested in another supported engine
- **THEN** that engine SHALL be selectable
- **AND** methodology packs SHALL require no change

#### Scenario: Data must remain as files
- **WHEN** data must stay as open-format files, or must not move from another cloud
- **THEN** the corresponding storage option SHALL be selectable per layer

### Requirement: Packs emit models, adapters emit artefacts
A methodology pack SHALL emit semantic models only, and an engine adapter SHALL render them
without making modelling decisions.

#### Scenario: Separation of concerns
- **WHEN** a methodology pack generates output
- **THEN** it SHALL emit a `semantic-model.v1` and SHALL NOT emit engine-specific artefacts
- **AND** the engine adapter SHALL NOT make modelling decisions

### Requirement: Compatibility is declared and implemented
A pack SHALL declare an engine for a role only when that engine's adapter implements the role.

#### Scenario: Streaming a history-bearing model
- **WHEN** a role requiring durable history is paired with a streaming engine
- **AND** the pack does not declare a streaming variant for that role
- **THEN** validation SHALL fail

### Requirement: Materialisation is an explicit decision
Every consumption model SHALL declare its materialisation, and the choice SHALL cite the BRD
freshness and volume answers.

#### Scenario: Choosing view versus materialised output
- **WHEN** a consumption model is defined without a materialisation
- **THEN** G1 SHALL fail
