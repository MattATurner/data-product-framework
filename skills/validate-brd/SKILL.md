---
skill_id: validate-brd
implements: brd-completeness
consumes: brd.yaml
produces: gaps.md
tool_tier: 4
tool: local
gate: G0
---

# Validate a BRD

Produce a mechanical G0 verdict and a gap register.

## Checks

| Check | Fails when |
|---|---|
| Rubric completeness | Any mandatory group A-K is unanswered |
| Acceptance examples | A business question has no worked example |
| Open questions | Any is unowned, or lacks a due date, assumption or blast radius |
| Modelling vocabulary | The BRD uses grain, SCD, dimension, surrogate key, partition, BigQuery |
| Source-field naming | A required output names a source column with no stated need |
| Conformance | A requested shared entity conflicts with `registry/conformance.yaml` |
| Glossary | A named term does not resolve |

## Output

`gaps.md` — each missing item phrased as **the question to put to the business**, with a
suggested owner. This is the requirements workshop agenda, not a defect list.

## Must

- Never guess at a missing answer.
- Distinguish blocking gaps from recorded assumptions; assumptions permit promotion to
  `provisional`, gaps do not.
