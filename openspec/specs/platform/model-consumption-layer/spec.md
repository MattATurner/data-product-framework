# Model Consumption Layer Specification

## Purpose

Methodology-neutral contract for the gold layer: what consumers actually receive.

## Requirements

### Requirement: Every output port is built
Every output port SHALL name a model in the manifest, and its port type SHALL agree with that
model's materialisation and access mechanism.

#### Scenario: Port without a model
- **WHEN** an output port names no model, or a model that does not exist
- **THEN** G1 SHALL fail

### Requirement: Business rules are enforced centrally
An exclusion the BRD states SHALL be enforced in the consumption model and SHALL NOT be left to
each consumer.

#### Scenario: Exclusion rule from the BRD
- **WHEN** the BRD states rows of a kind must be visible but excluded from a measure
- **THEN** the exclusion SHALL be enforced in the consumption model

### Requirement: Publication waits for blocking checks
Every published model SHALL depend on all blocking checks of its upstream models.

#### Scenario: A blocking check fails
- **WHEN** any blocking check upstream of an output port fails
- **THEN** that port SHALL NOT be refreshed

### Requirement: Backward compatibility
A breaking change to an output port SHALL require a major version and a published deprecation
window.

#### Scenario: Breaking change to an output port
- **WHEN** a column is removed or retyped, or the grain changes
- **THEN** a major version bump SHALL be required
- **AND** a deprecation window SHALL be published to registered consumers
