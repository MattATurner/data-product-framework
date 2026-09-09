# Customer Orders — Technical Design

**TDD-SALES-001** · owner: Data Analytics
**satisfies:** BRD-SALES-001@1.0.0 · **Version:** 1.0.0

## Methodology, engine and storage

### Requirement: No formal modelling methodology            [D-1] satisfies: R-1, R-5
The silver and gold layers SHALL use the `direct` pack.

*Rationale:* one source, one consumer group, current state sufficient (R-5), no
requirement to reconcile with another team. A dimensional model would add cost and buy
nothing. Domain default; no deviation, no ADR required.

### Requirement: Dataform on BigQuery native               [D-2] satisfies: R-6
Engine `dataform` and storage `bigquery_native` for all layers.

*Rationale:* pure SQL, daily batch, no external reader (R-8), no open-format requirement.

## Grain and shape

### Requirement: Order grain                                [D-3] satisfies: R-1, R-3
The consumption model SHALL be at the grain of **one row per customer order**, with grain
columns `(order_id)`. A uniqueness assertion SHALL be generated from those columns.

*Derivation:* the BRD states users drill to "a single customer order" and that "each
customer order appears once".

### Requirement: Order lines nested                         [D-4] satisfies: R-2
Order lines SHALL be nested on the order as `ARRAY<STRUCT<...>>` rather than held in a
separate table.

*Derivation:* R-2 requires lines to arrive with the order. Nesting preserves the 1:N
relationship, removes the join, and keeps the order grain intact. Cardinality is bounded
(typical order has under 20 lines), so the nesting rule is satisfied.

### Requirement: Latest state only                          [D-5] satisfies: R-3
Staging SHALL deduplicate on `order_id` taking the most recent source timestamp.
`history_semantics` is `current_only`.

*Derivation:* HB-1 states current details are acceptable; no point-in-time attribution is
required, so no slowly changing dimension behaviour is needed.

### Requirement: Cancelled orders retained and excluded     [D-6] satisfies: R-4
Cancelled orders SHALL be retained with `order_status = 'cancelled'`, and SHALL be
excluded from order-value aggregation **in the gold model**, not by the consumer.

## Materialisation and orchestration

### Requirement: Table, refreshed daily                     [D-7] satisfies: R-6
The gold model SHALL be built as a **table** on a daily schedule, before 07:00 local.

*Derivation:* about 25 users querying a few times daily makes a view wasteful (recompute
per read); freshness of next-morning makes streaming unnecessary. A materialized view is
not used because the nesting aggregation is better expressed as a scheduled build.

## Quality and access

### Requirement: Blocking quality rules                     [D-8] satisfies: R-7
`not_null` on customer reference and `range >= 0` on line quantity, both severity
`block`, plus `unique` on `order_id`. Gate behaviour `block`.

### Requirement: Internal access                            [D-9] satisfies: R-8
An authorized view exposed to Sales Operations and Data Analytics. No BigQuery sharing
listing.

## Feasibility

Source inspected via `mcp-toolbox-databases` (tier 2). Confirmed: `order_id` is unique
per file drop; a `last_modified_ts` exists to support D-5 deduplication; no customer
history is captured at source, which is consistent with R-5 requiring none.
