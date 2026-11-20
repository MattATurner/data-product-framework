# {Product name} — Technical Design Document

## Purpose

**TDD:** TDD-{DOMAIN}-{nnn} · **Satisfies:** BRD-{DOMAIN}-{nnn}@{x.y.z} · **Version:** {x.y.z} · **Owner:** {data team}

This Technical Design Document explains how {product name} is designed, decomposed, secured,
and operated on Google Cloud. Sections 1 to 8 are written in plain English with visual models
for architecture review boards, engineering leads, governance reviewers, and business-aligned
stakeholders. Machine-verifiable requirements, traceability matrices, and low-level physical
details live in Appendices A to D. The resolved machine-readable manifest is
`products/{product_id}/product.yaml`.

| Field | Value |
|---|---|
| Document ID & Version | TDD-{DOMAIN}-{nnn} · v{x.y.z} |
| Linked BRD | BRD-{DOMAIN}-{nnn}@{x.y.z} *(Use case: UC-{DOMAIN}-{nnn})* |
| Domain & Classification | {domain} · {INTERNAL / INTERNAL-COMMERCIAL / RESTRICTED} |
| Target Cloud Environment | Google Cloud · Project `{gcp-project-id}` · Region `{region}` |
| Accountable Business Owner | {business owner} |
| Technical Owner / Data Steward | {data team} |
| Review Sign-offs | Architecture Review · Data Governance / Security · Business Owner (`playback.md`) |

<!--
TDD v2 template · Design stage · Data Product Framework

Start from an approved BRD that passes G0 (`dpf brd validate {product}`). Save this file as
products/{product_id}/specs/tdd/spec.md and store rendered visual diagrams in
products/{product_id}/specs/tdd/assets/. The flagship worked example is
examples/sales_performance/specs/tdd/spec.md.

Workflow:
1. Run `dpf tdd resolve {product}` to see rubric derivations and the recommended methodology.
2. Inspect live source systems via the registered inspection tool (tier 2 MCP where available)
   and record results in Section 8 and Appendix D.
3. Produce the co-located visual views in `specs/tdd/assets/`:
   - `architecture.svg` — Solution & platform topology diagram
   - `functional-hierarchy.svg` — Modular Functional Hierarchy Diagram (FHD)
   - `data-flow.svg` — End-to-end runtime data flow & quality quarantine gate diagram
   - `entity-model.svg` — Crow's Foot Entity-Relationship & Dimensional Schema diagram
   - `dashboard-mockup.png` — (Optional, whenever BI / dashboards are in scope)
4. Write Sections 1 to 8 in plain English so an Architecture Review Board can understand every
   trade-off without reading SQL or YAML.
5. Complete Appendix A (`## Appendix A — Normative Technical Requirements`) with one
   `### Requirement:` block per decision (`D-1`..`D-n`), citing every active BRD requirement
   (`R-n`) and declaring **Model:** + **Grain:** for every consumption (gold) model.
6. Record any departure from registry/platform-defaults.yaml in an ADR (`templates/design/adr.md`).
7. Author `playback.md` (or `semantics.md`) and `product.yaml`, run Goldfish Pass G1, obtain
   business sign-off (`dpf signoff {product} --by "<name>" --role business_owner`), and verify
   with `dpf check {product} --gate G1`.

Replace every {placeholder} and delete these authoring comments before review.
-->

---

## 1. Executive Design Summary

### Business Objective and Scope

{Explain in 1–2 short plain-English paragraphs what business decisions this data product
enables, tracing directly to the BRD business questions (`BQ-1`..`BQ-n`).}

- **In scope:** {Summarise the core outputs, consumers, historical behaviour, and BI/sharing ports.}

- **Out of scope (Non-goals):** {Carry forward the BRD non-goals verbatim so boundaries are unmistakable.}

### Key Architectural Decisions at a Glance

| Business Need | Plain-English Design Choice | Rationale | Reference |
|---|---|---|---|
| {Shared definitions / history} | {Direct views vs. Kimball dimensional integration} | {Why this choice is right-sized for the BRD signals} | D-1, {ADR} |
| {Freshness & source connectivity} | {Capture mechanism and schedule} | {Feasibility & network constraints} | D-4, {ADR} |
| {Data trust & unusable rows} | {Quarantine reject relation + blocking gate} | {Consumers never see partial figures} | D-6 |
| {Sensitive attributes & access} | {Least-privilege roles + column masking / sharing listing} | {Protects restricted fields without blocking analysts} | D-7, D-8 |

---

## 2. Solution Architecture

<!-- Embed the rendered platform & network architecture diagram:
![{Product name} — Solution Architecture](assets/architecture.svg)
-->

### Plain-English Platform Walkthrough

- **Source & Network Boundary:** {Where source systems sit, connectivity path into Google Cloud, and why this transport pattern was selected.}

- **Raw, Staging & Core Warehouse Layers:** {How Google Cloud BigQuery layers separate immutable landing, deduplication/quarantine, integration, and consumption using the selected engine.}

- **Consumption & Presentation Plane:** {How internal BI tools, SQL analysts, or external sharing subscribers read published ports without direct warehouse coupling.}

- **Cross-Cutting Governance & Promotion:** {How Terraform, Knowledge Catalog, IAM, policy tags, and Cloud Monitoring govern the product across dev, test, and prod environments.}

---

## 3. Modular Functional Breakdown (FHD)

<!-- Embed the rendered Functional Hierarchy Diagram (FHD) showing chronological pillars and atomic delivery units:
![{Product name} — Modular Functional Breakdown](assets/functional-hierarchy.svg)
-->

{Optional link to interactive HTML explorer: `[Open Interactive FHD Explorer](assets/functional-hierarchy.html)`}

### Module Ownership Summary

{Explain in plain English how the data product is decomposed chronologically from left to right
into discrete build modules, enforcing single-writer ownership (`1 atomic persistence module : 1
primary write table`).}

| Pillar / Module UID | Capability / Module | Role | Primary Owned Table or Port | Plain-English Responsibility |
|---|---|---|---|---|
| {ACR}-01 | {Capture & Land} | Integration / Ledger | {raw / control tables} | {How source changes enter the platform} |
| {ACR}-02 | {Stage & Quality Gate} | Business Function / Ledger | {rejects table} | {Deduplication, quarantine, and blocking gate} |
| {ACR}-03 | {Core Modelling} | Persistence Modules | {silver / gold tables} | {History, conformance, and core calculations} |
| {ACR}-04 | {Consume & Govern} | Ports / Monitoring | {ports / catalog} | {User access, BI delivery, and SLO monitoring} |

---

## 4. End-to-End Data Flow & Processing Lifecycle

<!-- Embed the runtime data flow & quality quarantine diagram:
![{Product name} — End-to-End Runtime Data Flow](assets/data-flow.svg)
-->

### Capture and Refresh Cadence

{Explain in plain English how records leave the source system, how often extraction and
transformation run, and how duplicates or late-committing records are reconciled.}

### Quality Gate and Exception Handling

{Explain in plain English what constitutes an unusable record, where quarantined rows are
stored with their failure reason, and what consumers see when the blocking gate halts a run.}

### History, Amendments, and Corrections

{Explain point-in-time vs. current-state behaviour, exclusions such as cancelled items, and
any restatement window using one concrete dated example.}

---

## 5. Data Model & Entity Relationships

<!-- Embed the Crow's Foot Entity-Relationship diagram:
![{Product name} — Entity-Relationship Model](assets/entity-model.svg)
-->

{Optional link to interactive ER explorer: `[Open Interactive ER Model](assets/entity-model.html)`}

### Entity and Grain Summary

| Entity | Layer | Object Type | Plain-English Grain | History Behaviour | Primary Consumers |
|---|---|---|---|---|---|
| `{entity_name}` | {Silver / Gold} | {Fact / SCD2 Dim / Table / View / Sharing Port} | {One row per ...} | {Point-in-time / Current only} | {Who reads it} |

### Shared Definitions and Core Metrics

- **Conformed Definitions:** {Name any shared dimensions owned by or aligned with other business domains, and explain how late-arriving records are preserved safely.}

- **Core Business Calculations:** {Define headline metrics in plain English, stating what can be summed safely (additive vs. non-additive) and which exclusions are enforced centrally.}

---

## 6. Consumer Experience & Dashboard Mockups

<!-- Delete this section if the product exposes datasets only with no BI explores or dashboards. -->

### Output Ports and Access Summary

| Output Port | Type | Access Mechanism | Target Audience | Refresh Cadence |
|---|---|---|---|---|
| `{port_name}` | {BigQuery Table / Authorized View / Looker Explore / Looker Dashboard / BigQuery Sharing Listing} | {Dataset grant / Authorized view / Model set / Folder grant / Subscriber-only listing} | {Consumer groups} | {Hourly / Daily / Monthly} |

<!-- Embed an annotated low-clutter dashboard wireframe (illustrative sample figures):
![{Product name} — Dashboard Wireframe](assets/dashboard-mockup.png)
-->

### Stakeholder User Journeys

- **Answering {BQ-1}:** {Walk through how a user filters, compares periods, and reads headline KPIs.}

- **Explaining Anomalies ({BQ-2}):** {Walk through drilling from a summary figure down to underlying detail rows, noting reconciliation and masked fields.}

---

## 7. Security, Privacy & Data Governance

- **Classification and Residency:** {Product sensitivity classification and sovereign Google Cloud region boundary.}

- **Access Control and Least Privilege:** {Who reads what, OAuth / caller pass-through for BI, and isolated dataset boundaries for external sharing.}

- **Column-Level Protection:** {Which restricted attributes carry policy tags, what general analysts see (masked nulls/hashes), and which named group reads clear values.}

- **Catalog, Lineage, and Lifecycle:** {Registration in Knowledge Catalog with business glossary terms, ownership/stewardship, lineage edges, automated data quality scans, and retention/AGF controls where applicable.}

---

## 8. Operational Readiness, Feasibility & Risks

### Service Levels and Support

- **Freshness & Availability SLOs:** {Business-hours staleness target, check frequency, timezone, and overall availability objective.}

- **Alerting & Runbook:** {Which failures alert which channel, and pointer to the operational runbook (`RUNBOOK.md`).}

### Source Feasibility and Agreed Trade-offs

{Plain-English summary of live source inspection findings, any BRD constraint the source
cannot currently satisfy, what the business accepted in `playback.md`, and the non-breaking
future upgrade path.}

### Performance, Volume, and Cost Profile

{Expected daily/monthly row volumes, partitioning and clustering rationale in plain English,
and query-acceleration choices (for example governed rollups instead of ad-hoc BI PDTs).}

### Key Risks, Assumptions, and Dependencies

| Risk / Assumption | Impact | Mitigation / Owner |
|---|---|---|
| {e.g., Source lacks historical segment table} | {History starts at go-live; cannot backfill} | {Documented in `playback.md` Known limitations; Data Analytics} |

---

## Appendix A — Normative Technical Requirements

<!--
Machine-verifiable decision contract read by `dpf validate`, `dpf check --gate G1`, and `dpf trace`.
Keep the metadata keys directly beneath each `### Requirement:` heading:

  **Decision:**     D-n, unique in this file. Required.
  **Satisfies:**    BRD requirement IDs (R-n) served by this decision. Required.
  **Model:**        Model declared in product.yaml. Required for every gold model.
  **Grain:**        Model grain columns; must equal grain_columns in product.yaml.
  **Layer:** and **Methodology:**  Pair must match the layer's pack in product.yaml.
  **ADR:**          ADR ID also listed under adrs in product.yaml.

Every requirement MUST include SHALL or MUST and at least one `#### Scenario:` with bold
**WHEN** and **THEN** bullets. Repeat or delete blocks as needed to cover every active R-n.
-->

### Requirement: {Methodology for the layer}
**Decision:** D-1 · **Satisfies:** R-{n}, R-{n} · **Layer:** {silver | gold} · **Methodology:** {direct | kimball}

The {layer} layer SHALL use the `{pack}` pack. {Cite the BRD signals AG-n / HB-n and any ADR.}

#### Scenario: Recommendation matches the choice
- **WHEN** dpf evaluates the BRD signals for the {layer} layer
- **THEN** it SHALL recommend `{pack}`

### Requirement: {Business view} grain
**Decision:** D-2 · **Satisfies:** R-{n} · **Model:** {gold_model_name} · **Grain:** {column}, {column}

`{gold_model_name}` SHALL hold one row per {thing} per {thing}. A uniqueness check on the
grain columns SHALL block publication when duplicates exist.

#### Scenario: Figures add up
- **WHEN** figures are summed across all rows
- **THEN** the total SHALL equal the underlying detail total without double counting

### Requirement: {Attribute} keeps the value that applied at the time
**Decision:** D-3 · **Satisfies:** R-{n} · **Model:** {model_name}

`{model_name}` SHALL keep {attribute} as it was on the {event} date, while current-only
attributes SHALL reflect the latest source values.

#### Scenario: Attribute changes after an event
- **GIVEN** {a concrete dated example}
- **WHEN** the model is built
- **THEN** earlier figures SHALL stay with the earlier attribute value

### Requirement: {Capture method} for {source}
**Decision:** D-4 · **Satisfies:** R-{n} · **ADR:** {ADR-id}

Extraction from `{system_id}` SHALL use {snapshot | cdc | watermark | stream} capture on the
declared schedule. Rows read twice SHALL be removed by staging deduplication.

#### Scenario: Late or repeated rows
- **GIVEN** a row that commits late or is landed twice
- **WHEN** staging is built
- **THEN** it SHALL be counted once

### Requirement: Engine and storage
**Decision:** D-5 · **Satisfies:** R-{n}

Engine `{dataform}` and storage `{bigquery_native}` SHALL be used for every layer in project
`{gcp-project-id}`, region `{region}`.

#### Scenario: Engine implements every role
- **WHEN** the pipeline is composed
- **THEN** the `{engine}` adapter SHALL implement every role declared in the manifest

### Requirement: Unusable rows quarantined and publication blocked
**Decision:** D-6 · **Satisfies:** R-{n}

Rows failing quality validation SHALL be routed to a reject relation with their rule ID. Gate
behaviour SHALL be `{block | warn}`.

#### Scenario: Unusable row arrives
- **GIVEN** a row that violates rule `{QR-n}`
- **WHEN** the pipeline runs
- **THEN** the row SHALL appear in `{stg_model}_rejects` with reason `{QR-n}`
- **AND** downstream publication SHALL follow gate behaviour `{block | warn}`

### Requirement: {Restricted attributes} protected
**Decision:** D-7 · **Satisfies:** R-{n}

`{columns}` in `{model}` SHALL carry a policy tag whose masking rule protects restricted
values from general readers while authorised readers see clear values.

#### Scenario: Reader without fine-grained access
- **GIVEN** a member of `{group}`
- **WHEN** they select `{columns}` from `{model}`
- **THEN** the values SHALL be masked

### Requirement: {Output} published to {consumers}
**Decision:** D-8 · **Satisfies:** R-{n} · **Model:** {gold_model_name}

`{gold_model_name}` SHALL be published as a `{bigquery_table | bigquery_view | bigquery_sharing_listing}`
port with `{dataset_grant | authorized_view | sharing_listing}` access for `{consumers}`.

#### Scenario: Consumer access is least-privilege
- **WHEN** the port is published
- **THEN** `{consumers}` SHALL hold only the granted port access

### Requirement: Service levels and monitoring
**Decision:** D-9 · **Satisfies:** R-{n}

`{model}` SHALL be no more than `{staleness}` old during declared business hours, checked
every `{interval}`, and breaches SHALL alert the team channel.

#### Scenario: Freshness breach
- **GIVEN** the model exceeds its staleness limit during business hours
- **WHEN** the freshness check runs
- **THEN** an alert SHALL fire

---

## Appendix B — Traceability & Methodology Derivations

### Decision Coverage Matrix

| Design Area | Driven by (BRD Answer) | Platform Default | Decision | Recorded in `product.yaml` |
|---|---|---|---|---|
| Methodology per layer | Agreement with other teams; history behaviour | `direct` | D-1 | `layers.{layer}.methodology` |
| Grain of each model | Level of detail | — | D-2 | `grain_statement`, `grain_columns` |
| History semantics | History behaviour (`HB-n`) | `current_only` | D-3 | `history_semantics`, `attributes` |
| Capture & schedule | Freshness need; source feasibility | per source registry | D-4 | `sources`, `orchestration` |
| Engine & storage | External readers | `dataform`, `bigquery_native` | D-5 | `layers.*.engine`, `layers.*.storage` |
| Quality & quarantine | Fitness (`on_bad_data`) | gate `block` | D-6 | `quality` |
| Protection & access | Protection (`restricted_attributes`) | — | D-7 | `governance` |
| Output ports & sharing | Required outputs; external readers | dataset grant | D-8 | `output_ports` |
| Service levels & monitoring | Timeliness; fitness | — | D-9 | `observability` |

### Methodology Derivations

| BRD Signal | Why `direct` Cannot Serve It (or Confirmation That Default Holds) |
|---|---|
| {R-n / AG-n / HB-n} | {Justification from `dpf tdd resolve`} |

---

## Appendix C — Physical Implementation Reference

Authoritative machine-readable configuration lives in `products/{product_id}/product.yaml`.

### Dataset and Storage Inventory

| Layer | Dataset Key | Physical Dataset | Materialisation | Partition / Cluster / Window |
|---|---|---|---|---|
| Raw | `raw` | `{raw_dataset}` | Append-only native table | `DATE(_ingest_ts)` / `_source_pk_hash` |
| Staging | `staging` | `{stg_dataset}` | View + `_rejects` relation | Dedupe by `{dedupe_order}` |
| Silver | `silver` | `{slv_dataset}` | {Table / Incremental table} | {Partition / Cluster / Restatement window} |
| Gold | `gold` | `{gold_dataset}` | {Table / Authorized view} | {Schedule / Access} |

### Ingestion, Quarantine, Semantic Layer, and Infrastructure Summary

- **Extraction & Schedules:** {System ID, capture mode, watermark column, lookback minutes, cron expressions, timezone.}

- **Quarantine Rules (`QR-n`):** {Rule ID, target staging model, predicate, severity, and `on_fail` behaviour.}

- **Semantic Layer / BI Mapping:** {Explore base model, surrogate-key / `_dpf_pk` joins, aggregate table bindings, cache datagroup, and dashboard references (if applicable).}

- **Infrastructure & Governance Provisioning:** {Terraform module resources, IAM principal variables, policy tag taxonomy, and Knowledge Catalog registration method.}

---

## Appendix D — ADRs & Source Feasibility Evidence

### Architecture Decision Records

- **{ADR-DOMAIN-nnn-01}**: {One-line summary of the decision} (D-{n}).

### Live Source Inspection Evidence

Source inspected via `{MCP server or tool}` (tier {n}).

| Check | Finding |
|---|---|
| `{key columns}` uniqueness | {Confirmed unique / duplicates found} |
| Change timestamp available | {Column & type / none} |
| Source history retention | {Kept / current value only} |
| Continuous capture (CDC) feasible | {Yes / No and reason} |
| Estimated volume | {Rows per day} |

Consequences agreed with the business:

1. **{Topic}.** {Constraint raised, agreed BRD adjustment & version, and note in `playback.md`.}
