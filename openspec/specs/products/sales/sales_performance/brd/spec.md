# Sales Performance — Business Requirements

**BRD-SALES-002** · owner: Sales Operations · steward: Data Analytics
**Status:** approved · **Version:** 1.1.0

> Written by a business analyst. Contains no modelling vocabulary by design.

## Purpose

Sales leadership needs to understand which parts of the business are growing, measured
consistently with how Finance reports revenue and how Merchandising defines the product
range.

### Requirement: Segment performance                                  [R-1]
Users SHALL be able to see net sales by customer segment, product category and region,
for any period.

#### Example: Quarterly segment review                                [AX-1]
- A manager asks which customer segments grew net sales in Q1 versus Q4.
- They get net sales per segment for both quarters.

### Requirement: Drill to the individual line                         [R-2]
Users SHALL be able to drill from any total down to the individual line on a customer
order that contributed to it.

#### Example: Explaining a spike                                      [AX-2]
- A region shows an unexpected jump in March.
- The user drills to the individual order lines making up that March figure.

### Requirement: Each order line counted once                         [R-3]
Every line on a customer order SHALL be counted exactly once, however many times it was
amended.

#### Example: A line amended twice                                    [AX-3]
- A line is amended on Monday and again on Tuesday.
- It contributes once, at Tuesday's values.

### Requirement: Sales reflect the segment at the time of sale        [R-4]
When a customer moves between segments, sales already recorded SHALL continue to be
reported under the segment that applied on the date of the sale.

#### Example: Customer re-segmented after a sale                      [AX-4]
- A customer is "SMB" in March and reclassified "Enterprise" in June.
- March sales are still reported under "SMB".
- June sales are reported under "Enterprise".

### Requirement: Agreement with Finance                               [R-5]
Net sales figures SHALL reconcile with the revenue figures Finance reports for the same
period. Where the two differ, the difference SHALL be explainable.

#### Example: Month-end reconciliation                                [AX-5]
- Finance reports a March revenue total.
- Net sales for March reconciles to it, or the variance is explainable.

### Requirement: Agreement with the product range                     [R-6]
Product categories SHALL match the product range as Merchandising defines it, so that
category totals agree across teams.

### Requirement: Figures can be totalled                              [R-7]
Net sales SHALL be able to be added up across days, months, regions, categories and
segments without double counting.

### Requirement: Cancelled lines visible but not counted              [R-8]
Cancelled order lines SHALL remain visible for investigation, and SHALL NOT contribute
to net sales.

#### Example: A cancelled line                                        [AX-6]
- A line cancelled in April is visible in April's detail.
- It is excluded from April's net sales total.

### Requirement: Late corrections restate the period                  [R-9]
Corrections to a sale arriving within 90 days SHALL restate the affected period.
Corrections after 90 days SHALL NOT change published figures.

### Requirement: Same-day visibility of yesterday's sales             [R-10]
Sales SHALL be available hourly during the working day.

*Justification:* Sales Operations reallocate leads through the day, and a stale picture
causes duplicate customer outreach.

*Note (v1.1.0):* this requirement originally asked for availability within 15 minutes.
Design review established that the source system cannot currently be read that
frequently without network connectivity work that is not yet scheduled. The business
accepted **hourly** as sufficient for lead reallocation, on the basis that the shorter
interval can be delivered later without redesign. See the change record for BRD-SALES-002.

### Requirement: Incomplete sales must not be published               [R-11]
A sale with no customer recorded, or a negative quantity, is unusable. Publication SHALL
stop and alert rather than publish partial figures.

### Requirement: Analysts must not see customer contact details       [R-12]
Customer contact details SHALL NOT be visible to general analyst users, though the
customer's identity and segment SHALL be.

### Requirement: Monthly extract for the analytics partner            [R-13]
An external analytics partner SHALL receive a monthly extract. They are outside our
organisation and SHALL NOT be granted access to internal systems.

## Scope

**Non-goals:** forecasting and pipeline reporting; margin, cost or profitability
analysis; commission calculation.

## Open questions

None outstanding.
