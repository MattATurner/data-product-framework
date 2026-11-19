# Generate Artefacts Specification

## Purpose

Turn the approved design into executable artefacts deterministically, so that build output is a
function of the specification and can be regenerated, diffed and traced.

## Requirements

### Requirement: Generation is deterministic
Generating artefacts from unchanged inputs SHALL produce byte-for-byte identical output.

#### Scenario: Regenerate from scratch
- **WHEN** generated artefacts are deleted and regenerated from unchanged specs
- **THEN** the output SHALL be identical to the golden copy

### Requirement: Modelling decisions are generated, logic is authored
Grain, history handling, keys, materialisation, partitioning, access controls, assertions and
orchestration SHALL be generated from the manifest. Only business logic SHALL be authored by
hand, as engine-neutral SQL bodies.

#### Scenario: Grain assertion
- **WHEN** a model declares grain columns
- **THEN** the generated uniqueness assertion SHALL use exactly those columns

### Requirement: Artefacts carry their requirements
Every generated artefact SHALL carry a machine-readable list of the BRD requirements it serves.

#### Scenario: Tracing an artefact
- **WHEN** traceability is computed
- **THEN** each requirement SHALL be linked to the artefacts that carry it

### Requirement: Generation is bound to a build digest
Every generation SHALL record a digest of its inputs, and evidence SHALL be bound to that digest.

#### Scenario: Evidence from an older build
- **WHEN** test evidence was recorded against a different build digest
- **THEN** it SHALL be reported as stale
