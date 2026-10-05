# Traceability Specification

## Purpose

Guarantee that everything built is traceable to a business requirement, and that every business
requirement is designed, built, tested and proven — requirement to decision to design element to
artefact to test to evidence.

## Requirements

### Requirement: Bidirectional design coverage
Every BRD requirement SHALL be satisfied by at least one TDD decision and at least one manifest
element, and every decision and manifest element SHALL cite a BRD requirement or the platform
capability that mandates it (gate G1).

#### Scenario: Orphan requirement
- **WHEN** a BRD requirement has no decision or no design element
- **THEN** G1 SHALL fail
- **BECAUSE** something the business asked for is not being built

#### Scenario: Orphan design
- **WHEN** a TDD decision or manifest element cites no requirement and no platform capability
- **THEN** G1 SHALL fail
- **BECAUSE** something is being built that nobody asked for

### Requirement: Artefact and test coverage
Every BRD requirement SHALL be carried by at least one generated artefact, and every acceptance
scenario SHALL be verified by at least one test case (gate G3).

#### Scenario: Requirement designed but never built
- **WHEN** a requirement is cited in the manifest but no generated artefact carries it
- **THEN** G3 SHALL fail and name the requirement

#### Scenario: Scenario with no test
- **WHEN** an acceptance scenario has no automated, static or attested test
- **THEN** G3 SHALL fail

### Requirement: Specs are version-bound
A TDD SHALL declare the BRD version it satisfies, and a TDD bound to an earlier version SHALL be
treated as stale.

#### Scenario: BRD moves ahead of its TDD
- **WHEN** a BRD version is incremented
- **THEN** every TDD declaring an earlier version SHALL be marked stale
- **AND** SHALL be re-resolved and re-approved before build

### Requirement: Sign-off is bound to semantic content
The business sign-off on `semantics.md` SHALL record a digest of the semantic content, and any
change to that content SHALL invalidate the sign-off.

#### Scenario: Grain changes after sign-off
- **WHEN** a model's grain or history behaviour changes after sign-off
- **THEN** G1 SHALL fail until the business signs again

#### Scenario: TDD-only change
- **WHEN** a change alters only engineering detail and the semantic digest is unchanged
- **THEN** business re-approval SHALL NOT be required

### Requirement: The matrix is the acceptance pack
At G4 the traceability matrix SHALL show, per business requirement, the tests that prove it and
when they last passed against the current build.

#### Scenario: Acceptance at G4
- **WHEN** a product reaches G4
- **THEN** every requirement SHALL have passing evidence bound to the current build digest
