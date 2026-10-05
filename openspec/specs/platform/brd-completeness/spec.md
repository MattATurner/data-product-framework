# BRD Completeness Specification

## Purpose

Define what makes a business requirement document complete enough to design against, and make
that judgement mechanical rather than a matter of reviewer goodwill (gate G0).

## Requirements

### Requirement: Completeness is measured by questions answered
A BRD SHALL be complete only when every rubric group A to K has a business answer that
validates against the BRD contract.

#### Scenario: Missing level-of-detail answers
- **WHEN** a BRD does not state the finest level of detail required
- **THEN** G0 SHALL fail
- **AND** the gap register SHALL name the question to put to the business

#### Scenario: Freshness without justification
- **WHEN** a freshness target is stated with no business justification
- **THEN** G0 SHALL fail

### Requirement: Every requirement has an acceptance scenario
Every BRD requirement SHALL carry at least one business-language acceptance scenario with an
identifier, because acceptance scenarios become the tests.

#### Scenario: Requirement without an example
- **WHEN** a BRD requirement has no scenario
- **THEN** G0 SHALL fail and name the requirement

### Requirement: No modelling vocabulary
A BRD SHALL contain no modelling vocabulary and no warehouse product or region names.

#### Scenario: Engineer-authored grain
- **WHEN** a BRD states a grain, a history type or a conformed structure directly
- **THEN** validation SHALL fail
- **AND** the content SHALL move to the TDD as a derivation

### Requirement: Business terms and sources resolve
Every figure and attribute a BRD asks for SHALL resolve to a glossary term, and every system it
believes holds the data SHALL exist in the source registry.

#### Scenario: Unknown business term
- **WHEN** a required output names a figure that is not in the glossary
- **THEN** G0 SHALL fail and ask the business to define the term

### Requirement: Open questions are owned or blocking
An open question SHALL have an owner, a due date, a default assumption and a blast radius.

#### Scenario: Unowned open question
- **WHEN** an open question lacks any of owner, due date, assumption or blast radius
- **THEN** G0 SHALL fail

#### Scenario: Promoted with assumptions
- **WHEN** a BRD passes G0 with recorded assumptions
- **THEN** the resulting product SHALL be registered as `provisional`
- **AND** the assumptions SHALL be visible as a catalog aspect

### Requirement: The gap register is output, not specification
Validation SHALL write the gap register to the generated output area and SHALL NOT modify
files under `openspec/specs/`.

#### Scenario: Validating an incomplete BRD
- **WHEN** G0 finds gaps
- **THEN** the gap register SHALL be written under `generated/<product>/`
- **AND** the spec tree SHALL be unchanged
