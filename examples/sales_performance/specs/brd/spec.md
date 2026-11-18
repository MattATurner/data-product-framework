# Sales Performance — Business Requirements

## Purpose

**BRD:** BRD-SALES-002 · **Version:** 1.2.0 · **Status:** approved · **Owner:** Sales Operations · **Steward:** Data Analytics

Sales leadership needs to understand which parts of the business are growing, measured
consistently with how Finance reports revenue and how Merchandising defines the product
range.

> Written by a business analyst. Contains no modelling vocabulary by design. The structured
> answers to the completeness rubric (groups A to K) live in `brd.yaml` beside this file.

## Requirements

### Requirement: Segment performance
**ID:** R-1

Users SHALL be able to see net sales by customer segment, product category and region, for
any period.

#### Scenario: Quarterly segment review
**ID:** AX-1
- **GIVEN** sales recorded in two different quarters
- **WHEN** a manager asks which customer segments grew net sales between them
- **THEN** they get net sales per segment for both quarters, worked out the same way

### Requirement: Drill to the individual line
**ID:** R-2

Users SHALL be able to drill from any total down to the individual line on a customer order
that contributed to it.

#### Scenario: Explaining a spike
**ID:** AX-2
- **GIVEN** a region shows an unexpected jump in March
- **WHEN** the user drills into the March figure for that region
- **THEN** they see the individual order lines, and those lines add up to the figure

### Requirement: Each order line counted once
**ID:** R-3

Every line on a customer order SHALL be counted exactly once, however many times it was
amended.

#### Scenario: A line amended twice
**ID:** AX-3
- **GIVEN** a line is amended on Monday and again on Tuesday
- **WHEN** net sales are reported
- **THEN** the line contributes once, at Tuesday's values

### Requirement: Sales reflect the segment at the time of sale
**ID:** R-4

When a customer moves between segments or regions, sales already recorded SHALL continue to
be reported under the segment and region that applied on the date of the sale.

#### Scenario: Customer re-segmented after a sale
**ID:** AX-4
- **GIVEN** a customer is "SMB" in March and is reclassified "Enterprise" in June
- **WHEN** March and June sales are reported
- **THEN** March sales are still reported under "SMB"
- **AND** June sales are reported under "Enterprise"

### Requirement: Agreement with Finance
**ID:** R-5

Net sales figures SHALL reconcile with the revenue figures Finance reports for the same
period. Where the two differ, the difference SHALL be explainable.

#### Scenario: Month-end reconciliation
**ID:** AX-5
- **GIVEN** Finance reports a March revenue total
- **WHEN** net sales for March are compared with it
- **THEN** the two reconcile, or the variance is explained and accepted by Finance

### Requirement: Agreement with the product range
**ID:** R-6

Product categories SHALL match the product range as Merchandising defines it, so that
category totals agree across teams. A product that is recategorised SHALL keep its earlier
category for earlier sales.

#### Scenario: A product recategorised
**ID:** AX-7
- **GIVEN** a product sold in March is moved to a different category in June
- **WHEN** March and June sales are reported by category
- **THEN** March sales stay under the old category and June sales appear under the new one

#### Scenario: Categories confirmed by Merchandising
**ID:** AX-8
- **GIVEN** the list of product categories used in the figures
- **WHEN** Merchandising reviews it against their product range
- **THEN** Merchandising confirms the categories match

### Requirement: Figures can be totalled
**ID:** R-7

Net sales SHALL be able to be added up across days, months, regions, categories and segments
without double counting.

#### Scenario: Months add up to the year
**ID:** AX-9
- **GIVEN** monthly net sales for every region, category and segment
- **WHEN** they are added together
- **THEN** the total equals net sales counted directly from the individual order lines

### Requirement: Cancelled lines visible but not counted
**ID:** R-8

Cancelled order lines SHALL remain visible for investigation, and SHALL NOT contribute to net
sales.

#### Scenario: A cancelled line
**ID:** AX-6
- **GIVEN** a line is cancelled in April
- **WHEN** April is reported
- **THEN** the line is visible in April's detail, marked as cancelled
- **AND** it is excluded from April's net sales total

### Requirement: Late corrections restate the period
**ID:** R-9

Corrections to a sale arriving within 90 days SHALL restate the affected period. Corrections
after 90 days SHALL NOT change published figures.

#### Scenario: Corrections inside and outside the window
**ID:** AX-10
- **GIVEN** one sale corrected 30 days after it was made and another corrected 120 days after
- **WHEN** figures are next refreshed
- **THEN** the first correction changes its period's figures and the second does not

### Requirement: Hourly availability during the working day
**ID:** R-10

Sales SHALL be available hourly during the working day. Justification: Sales Operations
reallocate leads through the day, and a stale picture causes duplicate customer outreach.

#### Scenario: Figures are at most an hour behind
**ID:** AX-11
- **GIVEN** it is a working day between 08:00 and 18:00 Perth time
- **WHEN** a user looks at the figures
- **THEN** they include sales recorded up to about an hour earlier
- **AND** the team is alerted if they fall further behind

### Requirement: Incomplete sales must not be published
**ID:** R-11

A sale with no customer recorded, or a negative quantity, is unusable. Publication SHALL stop
and alert rather than publish partial figures.

#### Scenario: A sale with no customer
**ID:** AX-12
- **GIVEN** a new order line arrives with no customer recorded
- **WHEN** the figures are refreshed
- **THEN** the previously published figures stay as they were
- **AND** the team is alerted and can see the unusable line and the reason

### Requirement: Analysts must not see customer contact details
**ID:** R-12

Customer contact details SHALL NOT be visible to general analyst users, though the
customer's identity and segment SHALL be.

#### Scenario: An analyst looks up a customer
**ID:** AX-13
- **GIVEN** a general analyst
- **WHEN** they look at a customer's details
- **THEN** they see the customer's name and segment
- **AND** the email address and phone number are hidden

### Requirement: Monthly extract for the analytics partner
**ID:** R-13

An external analytics partner SHALL receive a monthly extract of net sales by month, product
category and region. They are outside our organisation and SHALL NOT be granted access to
internal systems.

#### Scenario: The partner receives a closed month
**ID:** AX-14
- **GIVEN** a month has closed
- **WHEN** the monthly extract is shared with the partner
- **THEN** they receive that month's figures without customer-level detail
- **AND** they have no access to any internal system

## Scope

**Non-goals:** forecasting and pipeline reporting; margin, cost or profitability analysis;
commission calculation.

## Open questions

None outstanding.
