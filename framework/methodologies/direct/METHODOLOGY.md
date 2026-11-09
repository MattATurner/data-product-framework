# Direct — no formal methodology

**Status:** default pack.

## When this is the right answer

- One source system, or several that need no reconciliation with each other.
- One consumer group.
- Current state is sufficient; nobody needs "as it was at the time".
- No requirement for numbers to agree with another team's numbers.

Take the raw tables, type and rename them, put a business view on top, and materialise
it if the query pattern justifies it. In BigQuery a 1:N relationship becomes an
`ARRAY<STRUCT>` on the parent rather than a fact/dimension split — the relationship is
preserved, the join disappears, and no surrogate-key machinery is needed.

**A methodology is a cost paid for a benefit.** Dimensional and vault modelling buy
conformance, history and auditability. If a product needs none of those, that ceremony
is pure overhead.

## What this pack does NOT relax

| Still required | Why |
|---|---|
| Declared, asserted grain | A business view has a grain too — one row per customer, per order, per claim |
| Signed `semantics.md` | The business still confirms what it receives |
| `semantic-model.v1` emitted | So gold, publish, catalog and quality skills work unchanged |
| Quality, classification, catalog, SLOs | Governance is not a function of modelling method |

This is *no methodology*, not *no design*. It skips restructuring, not rigour.

## Graduation triggers

| Signal | Graduate to |
|---|---|
| A second source must agree on the same entity | **Kimball** — conformed dimensions |
| Consumers need attribution "as at the time" rather than current state | **Kimball** SCD2, or a vault satellite |
| Audit or reconstruction obligations; source truth must be replayable | **Data Vault 2.0** |
| View chains deepening, or cost climbing with consumer count | Materialise first, then reconsider the model |

Because methodology lives in the TDD, graduating is a TDD-only change. If the derived
semantics are unchanged, `semantics.md` still reads the same and the business
re-approves nothing.
