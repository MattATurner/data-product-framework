# BRD Completeness Specification

## Purpose

Define what makes a business requirement document complete enough to design against,
and make that judgement mechanical rather than a matter of reviewer goodwill.

### Requirement: Completeness is measured by questions answered

A BRD SHALL be considered complete when every question the design depends on has a
business answer, across rubric groups A to K.

#### Scenario: Missing level-of-detail answers
- WHEN a BRD does not state the finest level of detail required
- THEN G0 SHALL fail
- AND the gap register SHALL name the question to put to the business.

#### Scenario: Missing history behaviour
- WHEN an attribute can change and the BRD does not state whether past figures follow it
- THEN G0 SHALL fail
- BECAUSE that answer determines history semantics.

#### Scenario: Freshness without justification
- WHEN a freshness target is stated with no business justification
- THEN G0 SHALL fail.

### Requirement: No modelling vocabulary

A BRD SHALL contain no modelling vocabulary.

#### Scenario: Engineer-authored grain
- WHEN a BRD states a grain, SCD type or conformed dimension directly
- THEN validation SHALL fail
- AND the content SHALL move to the TDD as a derivation.

### Requirement: Source-anchored requirements are surfaced

#### Scenario: BRD names a source field instead of a need
- WHEN a required output names a source column identifier
- THEN the gap register SHALL ask what business question the field answers
- AND the field SHALL be recorded as evidence, not as the requirement.

### Requirement: Open questions are owned or blocking

#### Scenario: Unowned open question
- WHEN an open question has no owner, due date, default assumption and blast radius
- THEN G0 SHALL fail.

#### Scenario: Promoted with assumptions
- WHEN a BRD passes G0 with recorded assumptions
- THEN the resulting product SHALL be registered as `provisional`
- AND the assumptions SHALL be visible as a catalog aspect.

### Requirement: Acceptance examples exist

#### Scenario: Business question without an example
- WHEN a business question has no worked acceptance example
- THEN G0 SHALL fail
- BECAUSE acceptance examples become the tests.
