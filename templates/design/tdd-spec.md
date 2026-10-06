# {Product name} — Technical Design

## Purpose

**TDD:** TDD-{DOMAIN}-{nnn} · **Satisfies:** BRD-{DOMAIN}-{nnn}@{x.y.z} · **Version:** {x.y.z} · **Owner:** {data team}

How {product name} is built: methodology per layer, grain, history, capture, engine,
storage, quality, protection, sharing and service levels. Every decision cites the BRD
requirements it satisfies. The resolved design is `products/{product_id}/product.yaml`.

<!--
TDD template · Design stage · Data Product Framework

Start from an approved BRD that passes G0 (`dpf brd validate {product}`). Save this file as
openspec/specs/products/{domain}/{product}/tdd/spec.md, or write it as a delta spec in an
OpenSpec change. The worked example is
openspec/specs/products/sales/sales-performance/tdd/spec.md.

1. Run `dpf tdd resolve {product}`. It shows how each BRD answer drives a design decision
   and which methodology the BRD signals recommend.
2. Inspect the real source before you decide how to capture it. Record what you find under
   "Feasibility finding".
3. Write one "### Requirement:" block for each decision. Keep the decision line exactly in
   the form shown, because dpf reads it.
4. Make sure that every BRD requirement (R-n) is satisfied by at least one decision.
5. Give every consumption (gold) model a decision with **Model:** and **Grain:**.
6. Record each departure from registry/platform-defaults.yaml in an ADR
   (templates/design/adr.md).
7. Write semantics.md and product.yaml from templates/design/.
8. Get the business owner to sign semantics.md. Then run `dpf check {product} --gate G1`.

Replace every {placeholder}. Delete these comments when you finish.
-->

## Requirements

<!--
The decision line. dpf reads these keys:

  **Decision:**     D-n, unique in this file. Required.
  **Satisfies:**    the BRD requirement ids (R-n) the decision serves. Required.
  **Model:**        a model declared in product.yaml. Required for each gold model.
  **Grain:**        the model's grain columns. Must equal grain_columns in product.yaml.
  **Layer:** and **Methodology:**  together; must match the layer's pack in product.yaml.
  **ADR:**          an ADR file that product.yaml also lists under adrs.

Each block needs a statement with SHALL and at least one scenario. Say why: cite the BRD
answers (AG-n, HB-n, the freshness need) and the platform default that you keep or leave.
The blocks below cover the usual design areas. Delete the ones that do not apply and repeat
the ones you need more than once, for example one grain decision for each gold model.
-->

### Requirement: {Methodology for the layer}
**Decision:** D-1 · **Satisfies:** R-{n}, R-{n} · **Layer:** {silver | gold} · **Methodology:** {direct | kimball}

The {layer} layer SHALL use the `{pack}` pack. {Why: name the BRD signals. If you keep the
`direct` default, say that no BRD answer asks for shared definitions or for values that
keep what applied at the time. If you leave it, cite the ADR and see Derivations.}

#### Scenario: Recommendation matches the choice
- **WHEN** dpf evaluates the BRD signals for the {layer} layer
- **THEN** it SHALL recommend `{pack}`

### Requirement: {Business view} grain
**Decision:** D-2 · **Satisfies:** R-{n} · **Model:** {gold_model_name} · **Grain:** {column}, {column}

`{gold_model_name}` SHALL hold one row per {thing} per {thing}. {From the BRD level of
detail: what the business drills to and what makes a row distinct.}

#### Scenario: {Figures add up}
- **WHEN** {the figures are summed across all rows}
- **THEN** {the total SHALL equal ... from the detail}

### Requirement: {Attribute} keeps the value that applied at the time
**Decision:** D-3 · **Satisfies:** R-{n} · **Model:** {model_name}

{From history behaviour HB-n.} `{model_name}` SHALL keep {attribute} as it was on the
{event} date. {Other attributes} SHALL show current values.

#### Scenario: {Attribute changes}
- **GIVEN** {a real example with dates, for example a customer moves segment on 2026-06-01}
- **WHEN** {the model is built}
- **THEN** {earlier figures SHALL stay with the old value}

### Requirement: {Capture method} for {source}
**Decision:** D-4 · **Satisfies:** R-{n} · **ADR:** {ADR-id, if this leaves the default}

{From the freshness need and the feasibility finding.} Extraction from `{system_id}` SHALL
use {snapshot | cdc | watermark | stream} capture {on a schedule}. {How rows read twice
are removed.}

#### Scenario: {Late or repeated rows}
- **GIVEN** {a row that is read twice, or that commits late}
- **WHEN** {the next extract runs}
- **THEN** {it SHALL be counted once after staging}

### Requirement: Engine and storage
**Decision:** D-5 · **Satisfies:** R-{n}

Engine `{dataform}` and storage `{bigquery_native}` SHALL be used for every layer, in
project `{gcp-project-id}`, region `{region}`. {Why. Name any reader outside the warehouse
that needs an open table format; if there is none, say so.}

#### Scenario: Engine implements every role
- **WHEN** the pipeline is composed
- **THEN** the {engine} adapter SHALL implement every role the manifest uses

### Requirement: Unusable rows quarantined and publication blocked
**Decision:** D-6 · **Satisfies:** R-{n}

{From the BRD fitness answers.} Rows that {condition} SHALL be routed to a reject relation
with a reason. {What a rejected row does to publication.} Gate behaviour is `{block | warn}`.

#### Scenario: {Unusable row}
- **GIVEN** {a new row with the condition}
- **WHEN** the pipeline runs
- **THEN** the row SHALL appear in `{stg_model}_rejects` with reason `{QR-n}`
- **AND** {no gold model SHALL be refreshed}

### Requirement: {Restricted attributes} protected
**Decision:** D-7 · **Satisfies:** R-{n}

{From the BRD protection answers.} `{columns}` in `{model}` SHALL carry a policy tag whose
masking rule {returns null | hashes the value} for {group}, while {group} reads clear values.

#### Scenario: {Reader without access}
- **GIVEN** a member of {group}
- **WHEN** they select {columns} from `{model}`
- **THEN** {the values SHALL be masked}

### Requirement: {Output} published to {consumers}
**Decision:** D-8 · **Satisfies:** R-{n} · **Model:** {gold_model_name}

`{gold_model_name}` SHALL be published as a `{bigquery_table | bigquery_view |
bigquery_sharing_listing}` port with `{dataset_grant | authorized_view | sharing_listing}`
access for {consumers}. {External readers get a sharing listing in its own dataset.}

#### Scenario: {Consumer access}
- **WHEN** the port is published
- **THEN** {consumers} SHALL {read it} and SHALL hold no other access

### Requirement: Service levels and monitoring
**Decision:** D-9 · **Satisfies:** R-{n}

{From the freshness need.} {Model} SHALL be no more than {time} old {during which hours and
days, in which time zone}, checked every {interval}. {Which failures alert which channel.}

#### Scenario: Freshness breach
- **GIVEN** {the model was last built too long ago, during business hours}
- **WHEN** the freshness check runs
- **THEN** an alert SHALL fire

## Decision coverage

<!-- One row for each design area. Name the decision that covers it, or say why it does not
apply. The "Driven by" column follows the derivations in registry/brd-rubric.yaml. -->

| Design area | Driven by (BRD answer) | Platform default | Decision | Recorded in product.yaml |
|---|---|---|---|---|
| Methodology per layer | Agreement with other teams; history behaviour | `direct` | D-1 | `layers.{layer}.methodology` |
| Grain of each model | Level of detail (drill to, distinct by) | — | D-2 | `grain_statement`, `grain_columns` |
| History | History behaviour (HB-n) | current values | D-3 | `history_semantics`, `attributes` |
| Totals | Totalling (can be summed across) | — | {D-n} | measure `additivity` |
| Inclusions, exclusions and corrections | Exceptions | — | {D-n} | `restatement_window_days`, flags |
| Capture and schedule | Freshness need; source registry; feasibility | per source registry | D-4 | `sources`, `orchestration` |
| Engine and storage | External readers | `dataform`, `bigquery_native` | D-5 | `layers.*.engine`, `layers.*.storage` |
| Materialisation | Expected users; peak volume | `view` in staging | {D-n} | `materialisation`, `partition_by` |
| Unusable rows and the quality gate | Fitness | gate `block` | D-6 | `quality` |
| Protection and access | Protection | — | D-7 | `governance` |
| Output ports and sharing | Required outputs; external readers | dataset grant | D-8 | `output_ports` |
| Service levels and monitoring | Freshness need; fitness | — | D-9 | `observability` |

## Derivations

<!-- Show why the methodology is what it is. Copy the recommendation from
`dpf tdd resolve {product}`. If you keep the `direct` default, write the single sentence
below and delete the table. If you leave the default, list each BRD signal that `direct`
cannot serve and cite the ADR. -->

D-1 is driven by these BRD signals:

| BRD signal | Why `direct` cannot serve it |
|---|---|
| {R-n / AG-n: figures must agree with another team} | {Needs a shared definition owned by one domain} |
| {R-n / HB-n: values must stay as they were} | {Needs attribute history, which a view over current source data cannot give} |

{Or: No BRD answer asks for shared definitions or for values that keep what applied at the
time, so the `direct` default holds.}

## Feasibility finding — raised against the BRD

Source inspected via `{MCP server or tool}` (tier {n}), {where and how it ran}.

| Check | Finding |
|---|---|
| `{key columns}` uniqueness | {Confirmed unique, or duplicates found} |
| Change timestamp available | {Column name, or none} |
| History of {attribute} at the source | {Kept, or current value only} |
| {Capture mode} feasible | {Yes, or no and why} |
| Rows per day | {Estimate} |

<!-- A requirement that the source cannot meet is a business issue, not an engineering
compromise. Raise it against the BRD in business language, agree the change with the
business owner and bump the BRD version. Never weaken a requirement silently. Put what the
business loses under "Known limitations" in semantics.md. -->

Consequences raised with the business:

1. **{Topic}.** {What cannot be met, what the business accepted, and the BRD version that
   records it.}

## Decision records

- **{ADR-DOMAIN-nnn-01}**: {The decision in one line} (D-{n}).
