# Sales Performance — Technical Design

**TDD-SALES-002** · owner: Data Analytics
**satisfies:** BRD-SALES-002@1.1.0 · **Version:** 1.0.0

## Methodology

### Requirement: Kimball dimensional in silver                [D-1] satisfies: R-4, R-5, R-6
The silver layer SHALL use the `kimball` pack.

*Derivation — this is a departure from the `direct` default and is justified by three
BRD signals, not by preference:*

| BRD signal | Why `direct` cannot serve it |
|---|---|
| R-5: net sales must reconcile with Finance | Requires a conformed, shared definition of the entities both teams count |
| R-6: categories must match Merchandising's range | Same — a shared product definition owned by one domain |
| R-4 / HB-1, HB-2: figures keep the segment and category that applied at the time | Requires attribute state to be preserved over time, which a typed view over current-state source data cannot provide |

Had any of these been absent, `direct` would have been correct and cheaper.
ADR-SALES-002-01 records the deviation from the domain default.

### Requirement: Direct business view in gold                 [D-2] satisfies: R-1, R-7
The gold layer SHALL use the `direct` pack with role `business_view` over the star.

*Rationale:* the modelling work is done in silver. Gold is presentation — semantic naming,
the cancelled-line exclusion, and aggregation. No second methodology is warranted.
Methodology is selected per layer, so this mixing is expected rather than exceptional.

## Grain and structure

### Requirement: Order line grain                             [D-3] satisfies: R-2, R-3
`fct_order_line` SHALL be at the grain of **one row per order line at its latest amended
values**, grain columns `(order_id, order_line_no)`. A uniqueness assertion SHALL be
generated from those columns.

*Derivation:* R-2 requires drill-down to "an individual line on a customer order"; R-3
requires each line to count once.

### Requirement: Customer dimension, point in time            [D-4] satisfies: R-4
`dim_customer` SHALL be a Type 2 slowly changing dimension with `valid_from`, `valid_to`,
`is_current`, a surrogate key and an unknown member.

*Derivation:* HB-1 states past sales keep the segment that applied on the sale date. Only
Type 2 preserves that. Type 1 would silently restate history and break AX-4.

### Requirement: Product dimension, point in time             [D-5] satisfies: R-6
`dim_product` SHALL be Type 2 on the same basis (HB-2), so category trends stay comparable.

### Requirement: Conformance registered                       [D-6] satisfies: R-5, R-6
`dim_customer` and `dim_product` SHALL be registered as conformed dimensions in
`registry/conformance.yaml`, owned by the sales domain. Any other product requesting them
at a different grain or key fails G0.

### Requirement: Transaction fact, additive measures          [D-7] satisfies: R-1, R-7
`fct_order_line` SHALL be a transaction fact. `net_amount` and `quantity` SHALL be declared
additive, so totalling across days, regions, categories and segments is safe.

Surrogate keys SHALL be resolved **as at the order date**, falling back to the unknown
member. Never null, never dropped.

`dim_date` is generated rather than sourced, and is therefore not listed in the manifest's
sourced models.

### Requirement: Cancelled lines retained, excluded in gold   [D-8] satisfies: R-8
Cancelled lines SHALL be retained in the fact with a status flag, and excluded from net
sales **in the gold model**, not by the consumer.

### Requirement: Partitioning and restatement                 [D-9] satisfies: R-9
`fct_order_line` SHALL be partitioned on order date and clustered on the customer and
product surrogate keys. Restatement SHALL rebuild only partitions within the 90-day
correction window.

## Capture, engine and storage

### Requirement: Hourly watermark capture                     [D-10] satisfies: R-10
Extraction SHALL use **watermark (incremental batch) capture on an hourly schedule**,
pulling over JDBC from `ora_local`.

*This is a constraint, not a preference.* See the feasibility finding below.

### Requirement: Dataform on BigQuery native                  [D-11] satisfies: R-10, R-13
Engine `dataform`, storage `bigquery_native`, project `data-product-framework`, region
`us-central1`, for all layers.

*Rationale:* pure SQL modelling; hourly batch; no engine other than BigQuery reads the
modelled layers. The partner extract is served by BigQuery sharing rather than an open
file format, so no Iceberg or Parquet requirement arises.

## Quality, protection and access

### Requirement: Blocking quality rules                       [D-12] satisfies: R-11
`not_null` on the customer reference, `range >= 0` on quantity, and `unique` on the fact
grain — all severity `block`, gate behaviour `block`.

### Requirement: Contact details protected                    [D-13] satisfies: R-12
Customer contact columns SHALL carry policy tags and be masked for the analyst role.
Customer identity and segment remain visible.

### Requirement: Partner extract via sharing                  [D-14] satisfies: R-13
The monthly partner extract SHALL be exposed as a **BigQuery sharing** listing, not an
authorized view, because the recipient sits outside the organisation and must not be
granted internal access.

## Feasibility finding — raised against the BRD

Source inspected via `mcp-toolbox-databases` (tier 2), running locally against the Oracle
JDBC URL.

| Check | Finding |
|---|---|
| `order_id, order_line_no` uniqueness | Confirmed unique |
| Change timestamp available | `last_modified_ts` present, suitable for watermarking |
| Customer segment history at source | **Not captured** — source holds current segment only |
| Continuous capture (CDC) feasible | **No** — the database is behind corporate NAT with no inbound route; Datastream cannot reach it. ARCHIVELOG and supplemental logging are also not enabled |

Two consequences, both handled as business issues rather than quiet engineering
compromises:

1. **Freshness.** The original 15-minute requirement could not be met. Raised to the
   business, who accepted hourly. BRD amended to 1.1.0; this TDD satisfies that version.
2. **Segment history.** The source does not retain it, so Type 2 tracking begins from
   first load and cannot be backfilled. Sales before go-live will carry the segment as at
   go-live. **This is a known limitation and is stated in `semantics.md`** so nobody
   discovers it during a variance investigation.

Both remain solvable later — CDC once connectivity exists — without redesigning the model.

## Decision records

- **ADR-SALES-002-01** — Kimball in silver, deviating from the `direct` domain default.
  Justified by R-4, R-5, R-6 as tabulated in D-1.
- **ADR-SALES-002-02** — Watermark capture instead of CDC. Driven by source reachability,
  reviewed when network connectivity changes.
