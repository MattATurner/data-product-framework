# Customer Orders — Business Requirements

## Purpose

**BRD:** BRD-SALES-001 · **Version:** 1.1.0 · **Status:** approved · **Owner:** Sales Operations · **Steward:** Data Analytics

Sales Operations needs a single, reliable view of customer orders to answer day-to-day
questions about what was ordered, by whom, and whether it was fulfilled.

> Written by a business analyst. Contains no modelling vocabulary by design. The structured
> answers to the completeness rubric (groups A to K) live in `brd.yaml` beside this file.

## Requirements

### Requirement: Order enquiry
**ID:** R-1

Users SHALL be able to look up any customer order and see who placed it, when, what was on
it, and its current status.

#### Scenario: Looking up an order
**ID:** AX-1
- **GIVEN** order `SO-10432` exists
- **WHEN** an operator searches for it
- **THEN** they see the customer, the order date, the status, and every line on that order
  with its product, quantity and amount

### Requirement: Order lines arrive with their order
**ID:** R-2

When a user retrieves an order, its lines SHALL be available with it rather than requiring a
separate lookup.

#### Scenario: One order, several lines
**ID:** AX-2
- **GIVEN** order `SO-10432` has three lines
- **WHEN** the order is retrieved
- **THEN** all three lines are returned together with it

### Requirement: Each order appears once
**ID:** R-3

Each customer order SHALL appear exactly once, showing its most recent state.

#### Scenario: An order amended twice
**ID:** AX-3
- **GIVEN** an order is amended on Monday and again on Tuesday
- **WHEN** it is looked up
- **THEN** it appears once, reflecting Tuesday's values

### Requirement: Cancelled orders remain visible
**ID:** R-4

Cancelled orders SHALL remain visible and clearly marked, but SHALL NOT count toward order
value totals.

#### Scenario: A cancelled order
**ID:** AX-4
- **GIVEN** an order is cancelled in April
- **WHEN** April is reviewed
- **THEN** the order is still findable and marked as cancelled
- **AND** it is excluded from April's total order value

### Requirement: Current state is sufficient
**ID:** R-5

Users SHALL see the customer's current details. There is no requirement to see what a
customer's details were at the time of an order.

#### Scenario: A customer changes address
**ID:** AX-5
- **GIVEN** a customer changes address in June
- **WHEN** their March order is looked up
- **THEN** it shows the customer's current address, which is acceptable

### Requirement: Next-day availability
**ID:** R-6

Orders SHALL be available the morning after they are placed. Justification: the team
reviews the prior day's orders in a morning stand-up; intraday availability would not change
any decision.

#### Scenario: Yesterday's orders at stand-up
**ID:** AX-6
- **GIVEN** orders placed during Monday
- **WHEN** the team meets at 07:00 on Tuesday
- **THEN** Monday's orders are available
- **AND** the team is alerted if they are not

### Requirement: Incomplete orders must not be published
**ID:** R-7

An order with no customer recorded, or with a negative quantity on any line, is unusable.
Publication SHALL stop and alert rather than publish partial data.

#### Scenario: A line with a negative quantity
**ID:** AX-7
- **GIVEN** an order arrives with a line whose quantity is negative
- **WHEN** the data is refreshed
- **THEN** the previously published orders stay as they were
- **AND** the team is alerted and can see the unusable order and the reason

### Requirement: Internal access only
**ID:** R-8

This is internal commercial information. Only Sales Operations and the Data Analytics team
SHALL be able to access it. There SHALL be no external sharing.

#### Scenario: Someone outside the two teams
**ID:** AX-8
- **GIVEN** a user who is in neither Sales Operations nor Data Analytics
- **WHEN** they try to read customer orders
- **THEN** access is refused

## Scope

**Non-goals:** forecasting; margin or cost analysis; anything about pipeline or
opportunities before an order exists.

## Open questions

None outstanding.
