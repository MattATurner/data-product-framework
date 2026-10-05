# Sales Performance — Technical Design

## Purpose

**TDD:** TDD-SALES-002 · **Satisfies:** BRD-SALES-002@1.2.0 · **Version:** 1.2.0 · **Owner:** Data Analytics

How the sales performance product is built: methodology per layer, grain, history, capture,
engine, storage, quality, protection, sharing and service levels. Every decision cites the
BRD requirements it satisfies. The resolved design is `products/sales_performance/product.yaml`.

## Requirements

### Requirement: Kimball dimensional in silver
**Decision:** D-1 · **Satisfies:** R-4, R-5, R-6 · **Layer:** silver · **Methodology:** kimball · **ADR:** ADR-SALES-002-01

The silver layer SHALL use the `kimball` pack. This departs from the `direct` platform
default because the BRD asks for figures shared with two other teams (AG-1, AG-2) and for
attributes that keep the value that applied at the time (HB-1 to HB-3). See Derivations.

#### Scenario: Recommendation matches the choice
- **WHEN** dpf evaluates the BRD signals for the silver layer
- **THEN** it SHALL recommend `kimball`
- **AND** the departure from the `direct` default SHALL be recorded in ADR-SALES-002-01

### Requirement: Direct business views in gold
**Decision:** D-2 · **Satisfies:** R-1, R-2, R-7 · **Layer:** gold · **Methodology:** direct

The gold layer SHALL use the `direct` pack. Modelling is done in silver; gold only names,
filters and aggregates for consumers, so no second methodology is warranted.

#### Scenario: Gold uses direct roles only
- **WHEN** gold models are composed
- **THEN** each SHALL use a role offered by the `direct` pack

### Requirement: Order line grain
**Decision:** D-3 · **Satisfies:** R-2, R-3 · **Model:** fct_order_line · **Grain:** order_id, order_line_no

`fct_order_line` SHALL hold one row per order line at its latest amended values. A uniqueness
check on the grain columns SHALL block publication when duplicates exist.

#### Scenario: Duplicate order line
- **GIVEN** two rows for the same order line
- **WHEN** the fact is built
- **THEN** the grain check SHALL fail and gold SHALL NOT be refreshed

### Requirement: Customer dimension keeps history
**Decision:** D-4 · **Satisfies:** R-4 · **Model:** dim_customer · **Grain:** customer_id, valid_from

`dim_customer` SHALL be a Type 2 dimension tracking customer segment and region, with validity
windows, a surrogate key and an unknown member. Name and contact details SHALL be current
values taken from the latest source row.

#### Scenario: Customer re-segmented
- **GIVEN** customer C-001 is SMB and becomes ENTERPRISE on 2026-06-01
- **WHEN** the dimension is built
- **THEN** it SHALL hold two versions whose validity windows do not overlap
- **AND** exactly one version SHALL be current

### Requirement: Product dimension keeps history
**Decision:** D-5 · **Satisfies:** R-6 · **Model:** dim_product · **Grain:** product_id, valid_from

`dim_product` SHALL be a Type 2 dimension tracking product category (HB-2), so category
trends stay comparable over time.

#### Scenario: Product recategorised
- **GIVEN** P-200 moves from GADGETS to WIDGETS on 2026-06-01
- **WHEN** the dimension and fact are built
- **THEN** March sales of P-200 SHALL resolve to GADGETS and June sales to WIDGETS

### Requirement: Conformance registered
**Decision:** D-6 · **Satisfies:** R-5, R-6

`dim_customer` and `dim_product` SHALL be registered as conformed dimensions owned by the
sales domain. A product declaring either at a different grain or key SHALL fail G1.

#### Scenario: Conflicting grain
- **GIVEN** another product declares `dim_customer` with a different natural key
- **WHEN** G1 runs for that product
- **THEN** it SHALL fail and name the owning domain

### Requirement: Transaction fact with additive measures
**Decision:** D-7 · **Satisfies:** R-1, R-7 · **Model:** fct_order_line

`fct_order_line` SHALL be a transaction fact whose measures (quantity, gross, discount and
net amount) are declared additive. Dimension keys SHALL be resolved as at the order date; a
missing member resolves to the unknown member and is reported, never dropped.

#### Scenario: Late-arriving customer
- **GIVEN** a line whose customer has not yet arrived in the dimension
- **WHEN** the fact is built
- **THEN** the line SHALL be kept with the unknown member
- **AND** a late-arrival warning SHALL be raised

### Requirement: Cancelled lines retained and excluded in gold
**Decision:** D-8 · **Satisfies:** R-8

Cancelled lines SHALL be kept in the fact with an `is_cancelled` flag and excluded from net
sales in the gold models, not by the consumer.

#### Scenario: Cancelled order
- **GIVEN** order SO-1003 is cancelled
- **WHEN** gold is built
- **THEN** SO-1003 SHALL appear in the line detail marked as cancelled
- **AND** April net sales SHALL exclude it

### Requirement: Partitioning and restatement window
**Decision:** D-9 · **Satisfies:** R-9 · **Model:** fct_order_line

`fct_order_line` SHALL be partitioned on order date and clustered on the customer and
product keys. Incremental builds SHALL rebuild only order dates inside the 90-day
correction window.

#### Scenario: Correction outside the window
- **GIVEN** a correction to a sale made 120 days ago
- **WHEN** the fact is rebuilt incrementally
- **THEN** that sale's partition SHALL NOT be rewritten

### Requirement: Hourly watermark capture
**Decision:** D-10 · **Satisfies:** R-10 · **ADR:** ADR-SALES-002-02

Extraction from `ora_local` SHALL use watermark capture on an hourly schedule with a
15-minute lookback, because the database has no inbound route from Google Cloud (see
Feasibility). Rows read twice SHALL be removed by staging deduplication.

#### Scenario: Late-committing transaction
- **GIVEN** a row committed with a change time just before the last watermark
- **WHEN** the next extract runs
- **THEN** the row SHALL be landed because it falls inside the lookback
- **AND** it SHALL be counted once after staging

### Requirement: Dataform on BigQuery native storage
**Decision:** D-11 · **Satisfies:** R-10, R-13

Engine `dataform` and storage `bigquery_native` SHALL be used for every layer, in project
`data-product-framework`, region `us-central1`. No reader outside the warehouse needs an
open table format; the partner is served by a sharing listing (D-14).

#### Scenario: Engine implements every role
- **WHEN** the pipeline is composed
- **THEN** the Dataform adapter SHALL implement every role the manifest uses

### Requirement: Unusable rows quarantined and publication blocked
**Decision:** D-12 · **Satisfies:** R-11

Order lines with no customer or a negative quantity SHALL be routed to a reject relation
with a reason. Any rejected row SHALL block the refresh of every gold model and raise an
alert. Gate behaviour is `block`.

#### Scenario: Line with no customer
- **GIVEN** a new order line with no customer
- **WHEN** the pipeline runs
- **THEN** the line SHALL appear in `stg_order_lines_rejects` with reason `QR-1`
- **AND** no gold model SHALL be refreshed
- **AND** the failed run SHALL raise an alert

### Requirement: Contact details masked for analysts
**Decision:** D-13 · **Satisfies:** R-12

Customer email and phone in `dim_customer` SHALL carry a policy tag whose masking rule
returns null to analysts, while a named contact group reads clear values. The line detail
view SHALL NOT expose contact columns.

#### Scenario: Analyst reads a customer
- **GIVEN** a member of the analyst group
- **WHEN** they select email and phone from `dim_customer`
- **THEN** both SHALL be null
- **AND** customer name and segment SHALL be visible

### Requirement: Partner extract via a sharing listing
**Decision:** D-14 · **Satisfies:** R-13 · **Model:** sales_performance_partner_extract · **Grain:** year_month, product_category, region

The partner extract SHALL hold closed months only, without customer detail, built monthly
into a dedicated sharing dataset and published as a sharing listing. The partner SHALL be
granted subscriber access to the listing and nothing else.

#### Scenario: Partner access is listing-only
- **WHEN** the extract is published
- **THEN** the partner principal SHALL hold only listing subscriber access
- **AND** it SHALL hold no dataset or project role

### Requirement: Monthly business view grain
**Decision:** D-15 · **Satisfies:** R-1, R-4, R-7 · **Model:** sales_performance_monthly · **Grain:** year_month, customer_segment, product_category, region

`sales_performance_monthly` SHALL hold one row per month, customer segment, product category
and region, using the segment, category and region that applied on the sale date.

#### Scenario: Monthly figures add up
- **WHEN** the monthly figures are summed across all rows
- **THEN** the total SHALL equal net sales from the non-cancelled lines of the fact

### Requirement: Line detail for drill-down
**Decision:** D-16 · **Satisfies:** R-2, R-8 · **Model:** sales_order_line_detail · **Grain:** order_id, order_line_no

`sales_order_line_detail` SHALL expose every order line, including cancelled ones, with the
segment, region and category that applied on the sale date, so any monthly figure can be
traced to its lines.

#### Scenario: Drill-down reconciles
- **WHEN** non-cancelled detail lines for one month, segment, category and region are summed
- **THEN** they SHALL equal that row of `sales_performance_monthly`

### Requirement: Staging deduplication
**Decision:** D-17 · **Satisfies:** R-3

Each staging model SHALL keep one row per natural key, choosing the latest source change
time and then the latest landing time, so amended and re-landed rows count once.

#### Scenario: Line landed three times
- **GIVEN** SO-1001 line 2 was landed three times with different values
- **WHEN** staging is built
- **THEN** one row SHALL remain, with quantity 6 and net amount 810.00

### Requirement: Service levels and monitoring
**Decision:** D-18 · **Satisfies:** R-10, R-11

Gold SHALL be no more than 90 minutes old between 08:00 and 18:00 Perth time on working
days, checked every 15 minutes. Daily volume, breaking schema drift, extract failures and
failed builds SHALL alert the sales data channel.

#### Scenario: Freshness breach
- **GIVEN** gold was last built two hours ago and it is 11:00 on a Tuesday
- **WHEN** the freshness check runs
- **THEN** an alert SHALL fire
- **AND** `dpf monitor` SHALL be able to open a change proposal for the breach

## Derivations

D-1 is driven by three BRD signals, not by preference:

| BRD signal | Why `direct` cannot serve it |
|---|---|
| R-5 / AG-1: net sales must reconcile with Finance | Needs a shared definition of the entities both teams count |
| R-6 / AG-2: categories must match Merchandising's range | Needs a shared product definition owned by one domain |
| R-4, R-6 / HB-1 to HB-3: figures keep the value that applied at the time | Needs attribute state preserved over time, which a typed view over current-state source data cannot provide |

Had any of these been absent, `direct` would have been correct and cheaper.

## Feasibility finding — raised against the BRD

Source inspected via `mcp-toolbox-databases` (tier 2), running locally against the Oracle
JDBC URL.

| Check | Finding |
|---|---|
| `order_id, order_line_no` uniqueness | Confirmed unique |
| Change timestamp available | `last_modified_ts` present, suitable for watermarking |
| Customer segment history at source | Not captured; the source holds current segment only |
| Continuous capture (CDC) feasible | No. The database is behind corporate NAT with no inbound route, and ARCHIVELOG and supplemental logging are not enabled |

Two consequences, both handled as business issues rather than quiet engineering compromises:

1. **Freshness.** The original 15-minute requirement could not be met. Raised to the
   business, who accepted hourly (BRD 1.1.0).
2. **Segment history.** The source does not retain it, so history begins at first load and
   cannot be backfilled. Sales before go-live carry the segment as at go-live. This is
   stated in `semantics.md`.

Both remain solvable later (CDC once connectivity exists) without redesigning the model.

## Decision records

- **ADR-SALES-002-01**: Kimball in silver, departing from the `direct` default (D-1).
- **ADR-SALES-002-02**: Watermark capture instead of CDC (D-10), reviewed when connectivity changes.
- **ADR-015** (platform): outbound-only watermark extractor written as bespoke code (tool tier 5).
