# Model Consumption Layer Specification

## Purpose

Methodology-neutral contract for the gold layer: what consumers actually receive.

### Requirement: Semantic naming

#### Scenario: Column naming
- WHEN a consumption model exposes a column
- THEN the name SHALL derive from the glossary where a term exists
- AND source-system identifiers SHALL NOT leak into output ports.

### Requirement: Business rules are enforced centrally

#### Scenario: Exclusion rule from the BRD
- WHEN the BRD states rows of a kind must be visible but excluded from a measure
- THEN the exclusion SHALL be enforced in the consumption model
- AND SHALL NOT be left to each consumer.

### Requirement: Backward compatibility

#### Scenario: Breaking change to an output port
- WHEN a column is removed or retyped, or the grain changes
- THEN a major version bump SHALL be required
- AND a deprecation window SHALL be published to registered consumers.
