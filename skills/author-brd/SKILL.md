---
name: author-brd
description: Interview a business owner and write a product BRD (spec.md plus brd.yaml) in business language
  only. Use when starting a new data product or when a BRD has gaps reported by dpf brd validate.
metadata:
  dpf:
    skill_id: author-brd
    stage: define
    scope: product
    implements: brd-completeness
    consumes: []
    produces:
    - brd.v1
    tool_tier: 4
    tool: dpf-local
    needs:
    - spec_validation
    owner: business-analyst
---

# Author a BRD

Elicit requirements in business language. The design is derived later from the answers,
so the questions quietly determine design without ever naming it.

## Ask, and what each answer determines

| Ask this | It quietly determines |
|---|---|
| "What is the finest level of detail you need to drill down to?" | grain |
| "Could two rows ever describe the same thing?" | grain columns |
| "If a customer moves segment, should last quarter's figures move with them?" | history semantics |
| "Must your numbers agree with another team's?" | conformance |
| "Can these figures be added across months? Regions?" | additivity |
| "How late can a correction arrive?" | restatement window |
| "If something is cancelled, should it disappear or stay visible?" | retention and exclusion |
| "Roughly how many people will use this, how often?" | materialisation |
| "Will anything other than your reporting tool read this?" | storage format and port type |

The full rubric (groups A to K) is `registry/brd-rubric.yaml`; methodology packs add
questions in `brd_elicitation_questions`.

## Write

- `openspec/specs/products/<domain>/<product>/brd/spec.md`: `## Purpose` with the
  `**BRD:** ... · **Version:** ...` line, then one `### Requirement:` per behaviour with an
  `**ID:** R-n` line, a SHALL statement and at least one `#### Scenario:` with an
  `**ID:** AX-n` line and GIVEN/WHEN/THEN bullets.
- `brd/brd.yaml` beside it: the structured answers (contract `brd.v1`).

## Source-anchored answers

When an analyst answers with a source field name, record it as evidence and ask "what
question does that field answer for you?". The answer is the requirement.

## Then

Run `dpf brd validate <product>` and take `generated/<product>/gaps.md` back to the business.
