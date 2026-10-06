# Worked example: the seed use-case portfolio

The three use cases from the seed use-case template, scored with
[`templates/scoring.yaml`](../../templates/scoring.yaml) and placed on the prioritisation
matrix. This example shows the Define stage, steps 2 and 3.

| File | What it is |
|---|---|
| [`portfolio.yaml`](portfolio.yaml) | the scores and decisions (the input) |
| [`scorecard.pdf`](scorecard.pdf) | the filled scorecard, with the scoring guide on page 1 |
| [`prioritisation.pdf`](prioritisation.pdf) | the matrix and the decision record |

## Result

| Use case | Value | Ease | Quadrant | Total (of 170) | Decision |
|---|---|---|---|---|---|
| UC-1 Develop new data product | 4.27 | 2.08 | Strategic bet | 119 (70%) | Approve for discovery; PRD |
| UC-2 Gather customer contact data | 2.55 | 1.67 | Deprioritise | 76 (45%) | Defer |
| UC-3 Share customer contact data with supplier | 2.73 | 2.33 | Deprioritise | 88 (52%) | Defer |

UC-1 matters most but is hard to deliver, so it goes to discovery first: agree the funding
and a delivery plan, and improve data readiness. UC-3 needs the data that UC-2 would gather,
and sharing personal data with a supplier needs a legal and privacy review.

## What is illustrative

- The first nine scores of each use case are the seed's own.
- The seed did not score **data readiness** or **delivery risk**, the two criteria that this
  framework adds. Those scores are invented to show how the criteria work, and are marked
  with † in the scorecard.
- The decisions are invented. The seed recorded no date, panel or decisions.

## A correction to the seed

With the seed's nine criteria alone, the totals are UC-1 101, UC-2 63 and UC-3 74. The seed
printed 98 for UC-1, but its rows add up to 101. The scorecard notes this.

## Rebuild

Edit `portfolio.yaml` and run `make templates`. See [`templates/README.md`](../../templates/README.md).
