# Worked example: from use case to design for sales_performance

This folder shows the Define stage for the `sales_performance` example product: the use
case, its score, the decision to go ahead and the BRD. The Design stage for the same product
is the real technical design in the repository. Together they trace one use case through to
a design that passes G1.

| Step | File | Source |
|---|---|---|
| 1 Use case | [`use-case.pdf`](use-case.pdf) | [`use-case.yaml`](use-case.yaml) |
| 2 Scorecard | [`scorecard.pdf`](scorecard.pdf) | [`portfolio.yaml`](portfolio.yaml) |
| 3 Prioritisation | [`prioritisation.pdf`](prioritisation.pdf) | [`portfolio.yaml`](portfolio.yaml) |
| 4a BRD | [`brd.pdf`](brd.pdf) | BRD-SALES-002 1.2.0: [`spec.md`](../../../openspec/specs/products/sales/sales-performance/brd/spec.md) and [`brd.yaml`](../../../openspec/specs/products/sales/sales-performance/brd/brd.yaml) |
| 5 TDD | TDD-SALES-002: [`spec.md`](../../../openspec/specs/products/sales/sales-performance/tdd/spec.md) | |
| 5 Business playback | [`semantics.md`](../../../openspec/specs/products/sales/sales-performance/tdd/semantics.md), signed in [`signoff.yaml`](../../../openspec/specs/products/sales/sales-performance/tdd/signoff.yaml) | |
| 5 Manifest and ADRs | [`product.yaml`](../../../products/sales_performance/product.yaml), [`adr/`](../../../products/sales_performance/adr/) | |

The product came first. UC-SALES-001 was written afterwards to show the whole chain, so:

- the use case takes its answers from BRD-SALES-002 where the BRD has them. Fields marked
  **Illustrative** in the PDF are invented;
- all scores and the decision are illustrative: value 3.05, ease 3.33, a **Quick win**,
  107 of 170 (63%);
- `brd.pdf` is the approved BRD record, read from the repository, shown in the BRD template.
  Only the link to the use case is added.

## Trace: use case to BRD to TDD

| What the use case needs | BRD | TDD decisions |
|---|---|---|
| Net sales agree with Finance | R-5, AG-1 | D-1, D-6 |
| Categories agree with Merchandising | R-6, AG-2, HB-2 | D-1, D-5, D-6 |
| Segment investment each quarter | BQ-1, R-1, R-4, HB-1, HB-3 | D-2, D-4, D-15 |
| Range and territory planning | BQ-2, R-1, R-6 | D-2, D-5, D-15 |
| Trace a figure to its lines at month end | BQ-3, R-2, R-3 | D-3, D-16, D-17 |
| Fresh figures, to stop duplicate outreach | R-10 | D-10, D-18 |
| Monthly extract for the partner | R-13 | D-11, D-14 |
| No contact details for general analysts | R-12 | D-13 |

## What the design found

The use case scored data readiness 4 out of 5 (an illustrative score). Its risks and its
approval both said what was not yet known: how often the sales system can be read, and
whether it keeps a history of segment changes. The feasibility pass in the TDD answered both:

1. **The sales system cannot be reached from Google Cloud**, so continuous capture is not
   possible. The BRD asked for figures 15 minutes old. That was raised with the business, who
   accepted hourly figures, and the BRD moved to 1.1.0.
2. **The sales system keeps only the current segment.** History starts when the product goes
   live. `semantics.md` says so under "Known limitations", on the page that the business
   owner signs.

A data-readiness score is a belief. The design tests it against the real source, and what it
finds goes back to the business as a change to the BRD, never as a quiet compromise.

## Rebuild

Edit the YAML files and run `make templates`. See [`templates/README.md`](../../../templates/README.md).
