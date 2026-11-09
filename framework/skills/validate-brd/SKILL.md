---
name: validate-brd
description: 'Run the G0 gate on a BRD: rubric completeness, one scenario per requirement, business vocabulary,
  glossary and source checks, and a gap register phrased as questions for the business. Use before any
  design work starts.'
metadata:
  dpf:
    skill_id: validate-brd
    stage: define
    scope: product
    implements: brd-completeness
    consumes:
    - brd.v1
    produces: []
    tool_tier: 4
    tool: dpf-local
    needs:
    - spec_validation
    gate: G0
---

# Validate a BRD (G0)

```bash
dpf brd validate <product>
```

## Checks

| Check | Fails when |
|---|---|
| Contract | `brd.yaml` does not validate against `brd.v1` |
| Rubric completeness | A group A to K in `registry/brd-rubric.yaml` is unanswered |
| Acceptance scenarios | A requirement has no `#### Scenario:` with an `**ID:** AX-n` line |
| Vocabulary | The BRD uses modelling or technology terms, or an infrastructure region (`registry/brd-vocabulary.yaml`) |
| Glossary | A figure or attribute in `required_outputs` matches no glossary term or alias |
| Sources | A `sources_believed` system is not in the source registry |
| Open questions | An open question lacks an owner, a due date or an assumption |

## Output

`generated/<product>/gaps.md`: each gap phrased as **the question to put to the business**.
It is the workshop agenda, not a defect list, and it is never written into the spec tree.

## Must

- Never guess a missing answer.
- Distinguish blocking gaps from recorded assumptions: assumptions allow `provisional`, gaps do not.
