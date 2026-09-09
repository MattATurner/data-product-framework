# Customer Orders — Business Requirements

**BRD-SALES-001** · owner: Sales Operations · steward: Data Analytics
**Status:** approved · **Version:** 1.0.0

> Written by a business analyst. Contains no modelling vocabulary by design.

## Purpose

Sales Operations needs a single, reliable view of customer orders to answer day-to-day
questions about what was ordered, by whom, and whether it was fulfilled.

### Requirement: Order enquiry                                        [R-1]
Users SHALL be able to look up any customer order and see who placed it, when, what was
on it, and its current status.

#### Example: Looking up an order                                     [AX-1]
- An operator searches for order `SO-10432`.
- They see the customer, the order date, the status, and every line on that order with
  its product, quantity and amount.

### Requirement: Order lines arrive with their order                  [R-2]
When a user retrieves an order, its lines SHALL be available with it rather than
requiring a separate lookup.

#### Example: One order, several lines                                [AX-2]
- Order `SO-10432` has three lines.
- Retrieving that order returns all three lines together.

### Requirement: Each order appears once                              [R-3]
Each customer order SHALL appear exactly once, showing its most recent state.

#### Example: An order amended twice                                  [AX-3]
- An order is amended on Monday and again on Tuesday.
- It appears once, reflecting Tuesday's values.

### Requirement: Cancelled orders remain visible                      [R-4]
Cancelled orders SHALL remain visible and clearly marked, but SHALL NOT count toward
order value totals.

#### Example: A cancelled order                                       [AX-4]
- An order cancelled in April is still findable in April.
- It is excluded from April's total order value.

### Requirement: Current state is sufficient                          [R-5]
Users need the customer's current details. There is no requirement to see what a
customer's details were at the time of an order.

#### Example: A customer changes address                              [AX-5]
- A customer changes address in June.
- Their March order shows the customer's current address. This is acceptable.

### Requirement: Next-day freshness                                   [R-6]
Orders SHALL be available the morning after they are placed.

*Justification:* the team reviews the prior day's orders in a morning stand-up. Intraday
freshness has no business use here and would not change any decision.

### Requirement: Incomplete orders must not be published              [R-7]
An order with no customer recorded, or with a negative quantity on any line, is unusable.
Publication SHALL stop and alert rather than publish partial data.

### Requirement: Internal access only                                 [R-8]
This is internal commercial information. Only Sales Operations and the Data Analytics
team may access it. No external sharing.

## Scope

**Non-goals:** forecasting; margin or cost analysis; anything about pipeline or
opportunities before an order exists.

## Open questions

None outstanding.
