# Customer Orders — Technical Design

## Purpose

**TDD:** TDD-SALES-001 · **Satisfies:** BRD-SALES-001@1.1.0 · **Version:** 1.1.0 · **Owner:** Data Analytics

How the customer orders product is built. One source, one consumer group and current state
only, so the design stays deliberately simple. The resolved design is
`products/customer_orders/product.yaml`.

## Requirements

### Requirement: No formal modelling methodology
**Decision:** D-1 · **Satisfies:** R-1, R-5 · **Layer:** gold · **Methodology:** direct

The consumption layer SHALL use the `direct` pack and there SHALL be no integration layer.
One source, one consumer group, current state sufficient (R-5) and no agreement needed with
another team: a dimensional model would add cost and buy nothing.

#### Scenario: Recommendation matches the choice
- **WHEN** dpf evaluates the BRD signals
- **THEN** it SHALL recommend `direct`
- **AND** no decision record SHALL be needed because `direct` is the platform default

### Requirement: Dataform on BigQuery native storage
**Decision:** D-2 · **Satisfies:** R-6, R-8

Engine `dataform` and storage `bigquery_native` SHALL be used for every layer. The work is
pure SQL in a daily batch, with no external reader and no open-format requirement.

#### Scenario: Engine implements every role
- **WHEN** the pipeline is composed
- **THEN** the Dataform adapter SHALL implement every role the manifest uses

### Requirement: Order grain
**Decision:** D-3 · **Satisfies:** R-1, R-3 · **Model:** customer_orders · **Grain:** order_id

The consumption model SHALL hold one row per customer order. A uniqueness check on `order_id`
SHALL block publication when duplicates exist.

#### Scenario: Duplicate order
- **GIVEN** two rows for the same order
- **WHEN** the model is built
- **THEN** the grain check SHALL fail and the model SHALL NOT be published

### Requirement: Order lines nested
**Decision:** D-4 · **Satisfies:** R-2 · **Model:** customer_orders

Order lines SHALL be nested on the order as a repeated record rather than held in a separate
table. Nesting keeps the order grain and removes a join; a typical order has under 20 lines.

#### Scenario: Lines arrive with the order
- **GIVEN** an order with three staged lines
- **WHEN** the order is read
- **THEN** its nested lines SHALL number three

### Requirement: Latest state only
**Decision:** D-5 · **Satisfies:** R-3, R-5

Staging SHALL keep one row per natural key, choosing the latest source change time and then
the latest landing time. Every model SHALL declare `current_only` history.

#### Scenario: Order amended twice
- **GIVEN** an order landed three times with different statuses
- **WHEN** staging is built
- **THEN** one row SHALL remain, with the latest status

### Requirement: Cancelled orders retained and excluded
**Decision:** D-6 · **Satisfies:** R-4

Cancelled orders SHALL be kept and marked `is_cancelled`, and their `counted_order_value`
SHALL be zero so totals exclude them in the model, not in the consumer.

#### Scenario: Cancelled order
- **GIVEN** a cancelled order
- **WHEN** the model is built
- **THEN** it SHALL be present with `is_cancelled` true and `counted_order_value` zero

### Requirement: Table refreshed daily
**Decision:** D-7 · **Satisfies:** R-6

The consumption model SHALL be a table built daily at 06:00 Perth time. About 25 users
querying a few times a day makes a view wasteful, and next-morning freshness makes streaming
unnecessary.

#### Scenario: Built before stand-up
- **WHEN** the daily schedule runs at 06:00
- **THEN** the table SHALL be rebuilt before 07:00

### Requirement: Unusable orders quarantined and publication blocked
**Decision:** D-8 · **Satisfies:** R-7

Orders with no customer and lines with a negative quantity SHALL be routed to reject
relations with a reason, and any rejected row SHALL block the refresh of the consumption
model and raise an alert. Gate behaviour is `block`.

#### Scenario: Negative quantity
- **GIVEN** a staged line with quantity -1
- **WHEN** the pipeline runs
- **THEN** the line SHALL appear in `stg_order_lines_rejects` with reason `QR-2`
- **AND** the consumption model SHALL NOT be refreshed

### Requirement: Internal access
**Decision:** D-9 · **Satisfies:** R-8

Read access SHALL be granted on the consumption dataset to the Sales Operations and Data
Analytics groups only. There SHALL be no sharing listing.

#### Scenario: Access list
- **WHEN** the product is deployed
- **THEN** only the two groups SHALL hold read roles on the consumption dataset

### Requirement: Service levels and monitoring
**Decision:** D-10 · **Satisfies:** R-6, R-7

The consumption model SHALL be no more than 13 hours old between 07:00 and 18:00 Perth time
on any day, checked hourly. Failed builds and rejected rows SHALL alert the team.

#### Scenario: Missed overnight build
- **GIVEN** the 06:00 build failed
- **WHEN** the freshness check runs at 07:00
- **THEN** an alert SHALL fire

## Feasibility

Source inspected by listing the object drop (no MCP server is needed for object listings).
Confirmed: `order_id` is unique per file drop; `last_modified_ts` exists to support D-5
deduplication; no customer history is captured at source, which is consistent with R-5
requiring none.
