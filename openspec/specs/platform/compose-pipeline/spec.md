# Compose Pipeline Specification

## Purpose

Resolve a product manifest into an ordered chain of skills, and prove the chain is
valid before anything executes.

### Requirement: Contract compatibility

#### Scenario: Mismatched handoff
- WHEN a skill's produced contract does not satisfy the next skill's consumed contract
- THEN composition SHALL fail with both contract ids named
- AND no artefact SHALL be generated.

#### Scenario: Valid chain
- WHEN every handoff type-checks
- THEN composition SHALL emit the ordered skill DAG
- AND the DAG SHALL be reproducible from the same manifest.

### Requirement: Methodology and engine compatibility

#### Scenario: Unsupported combination
- WHEN a manifest pairs a methodology role with an engine the pack does not declare support for
- THEN composition SHALL fail at G1
- BECAUSE generating code that compiles but misbehaves is worse than failing.

### Requirement: Reproducibility

#### Scenario: Regenerate from scratch
- WHEN generated artefacts are deleted and the chain is re-run against an unchanged
  BRD and TDD
- THEN the output SHALL be byte-for-byte identical.
