# Traceability Specification

## Purpose

Guarantee that everything built is traceable to a business requirement, and that every
business requirement is built and tested.

### Requirement: Bidirectional coverage

#### Scenario: Orphan requirement
- WHEN a BRD requirement has no derivation, design decision or test
- THEN G1 SHALL fail
- BECAUSE something the business asked for is not being built.

#### Scenario: Orphan design
- WHEN a TDD decision or skill invocation cites no BRD requirement id
- THEN G1 SHALL fail
- BECAUSE something is being built that nobody asked for.

### Requirement: Specs are version-bound

A TDD SHALL declare `satisfies: <brd_id>@<version>`.

#### Scenario: BRD moves ahead of its TDD
- WHEN a BRD version is incremented
- THEN every TDD declaring an earlier version SHALL be marked stale
- AND SHALL be re-resolved and re-approved before build.

#### Scenario: TDD-only change
- WHEN a change alters only the TDD and the derived semantics are unchanged
- THEN business re-approval SHALL NOT be required
- AND the engineering lead alone MAY approve.

### Requirement: The matrix is the acceptance pack

#### Scenario: Acceptance at G4
- WHEN a product reaches G4
- THEN the traceability matrix SHALL show, per business requirement, the test that
  proves it and when it last passed.
