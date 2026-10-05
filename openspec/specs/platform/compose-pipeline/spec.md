# Compose Pipeline Specification

## Purpose

Resolve a product manifest into a typed graph of skill invocations, chosen by stage and instance
rather than by a fixed list, and prove the graph is valid before anything executes.

## Requirements

### Requirement: Skills are selected, not hard-coded
Composition SHALL select, for every stage and every instance (source, model or product), the
skills whose declared selection conditions match that instance.

#### Scenario: Relational source with watermark capture
- **WHEN** a source is a relational database captured by watermark
- **THEN** the relational watermark extract skill SHALL be selected
- **AND** the object-store extract skill SHALL NOT be selected

#### Scenario: No skill or several skills match
- **WHEN** no skill, or more than one skill, matches a required stage for an instance
- **THEN** composition SHALL fail and name the instance and the candidates

### Requirement: Contract compatibility
Every edge of the composed graph SHALL type-check: the consuming skill SHALL declare the
contract its upstream produces.

#### Scenario: Mismatched handoff
- **WHEN** a skill's produced contract is not consumed by the downstream skill
- **THEN** composition SHALL fail with both contract ids named
- **AND** no artefact SHALL be generated

#### Scenario: Valid graph
- **WHEN** every edge type-checks
- **THEN** composition SHALL emit the graph in a deterministic order

### Requirement: Methodology, engine and adapter compatibility
A model SHALL compose only when its pack declares the engine for its role and the engine
adapter implements that role.

#### Scenario: Unsupported combination
- **WHEN** a manifest pairs a role with an engine the pack does not declare
- **THEN** composition SHALL fail at G1

#### Scenario: Declared but unimplemented
- **WHEN** a pack declares an engine whose adapter does not implement the role
- **THEN** validation SHALL fail
- **BECAUSE** compatibility is declared, not assumed
