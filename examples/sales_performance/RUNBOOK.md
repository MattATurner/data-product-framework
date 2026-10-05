# Runbook — sales_performance

Local Oracle to BigQuery in `data-product-framework` / `us-central1`.

| | |
|---|---|
| BRD | `openspec/specs/products/sales/sales-performance/brd/spec.md` (BRD-SALES-002 @ 1.2.0) |
| TDD | `openspec/specs/products/sales/sales-performance/tdd/spec.md` (TDD-SALES-002) |
| Signed semantics | `.../tdd/semantics.md`, signature in `.../tdd/signoff.yaml` |
| Manifest | `products/sales_performance/product.yaml` |
| Acceptance | `products/sales_performance/acceptance.yaml` (AT-1 … AT-14) |

## 0. Check the specs before building anything

```bash
dpf check sales_performance --gate G3
```

G0 (BRD complete), G1 (design resolves the BRD, sign-off current), G2 (pipeline composes,
every scenario has a test) and G3 (artefacts generate, match the golden copy, every
requirement traces to an artefact and a test) all pass before any SQL runs. If this is red,
stop.

## 1. Generate and deploy the infrastructure

```bash
dpf generate sales_performance                 # generated/sales_performance/{dataform,terraform,...}
cd examples/sales_performance/terraform
cp terraform.tfvars.example terraform.tfvars   # groups, Dataform repository, alert channel
terraform init && terraform apply
```

Seven datasets (raw, staging, silver, gold, share, assertions, control), the control
tables, the `pii/contact` policy tag with a null mask for analysts (R-12), the partner
listing (R-13), orchestration, checks, alerts and Knowledge Catalog quality scans. Apply
before the first extract: the extractor writes to the control tables.

Push `generated/sales_performance/dataform/` to the default branch of the Dataform
repository named in `dataform_repository`.

## 2. Data in — pick one

### Option A: seed fixtures (no Oracle needed)

Start here. It proves the whole chain and exercises the automated acceptance tests.

**Load in phases and build between them.** A Type 2 dimension records history as changes
*arrive*. Loading both states at once lets staging collapse them, and the earlier version
is never recorded. The phased seed exists to prevent exactly that mistake.

```bash
cd examples/sales_performance/seed
python3 generate_seed.py --phase 1 --load   # the world as at end of May
#   build (step 3)
python3 generate_seed.py --phase 2 --load   # 1 June: C-001 re-segmented, P-200 recategorised
#   build again: history now exists
```

After phase 2, `dim_customer` holds two rows for `C-001`:

| customer_segment | valid_from | valid_to |
|---|---|---|
| SMB | 1900-01-01 | 2026-06-01 |
| ENTERPRISE | 2026-06-01 | 9999-12-31 |

The first version opens at a floor date, so historical facts resolve to it rather than to
the unknown member. Later versions open at the **source change timestamp**, not the load
time. That is what makes AX-4 and AX-7 correct.

Phase 3 (`--phase 3`) adds order SO-1005 with no customer. Load it **after** recording
evidence (step 4): it shows the reject gate stopping publication (AX-12).

### Option B: the real Oracle

```bash
pip install oracledb google-cloud-bigquery pyyaml jsonschema
export ORACLE_USER=... ORACLE_PASSWORD=...
cd examples/sales_performance/extract
python3 extract_oracle.py --dry-run     # reads Oracle only; prints the manifests
python3 extract_oracle.py               # all entities
```

Outbound only (ADR-015). Each batch commits raw rows, watermark and landing manifest in one
BigQuery transaction, so a failed run commits nothing and is safe to repeat. See
`extract/README.md` for delivery semantics and drift handling.

## 3. Build the models

Scheduled runs come from the workflow configurations Terraform created (`hourly` at
:10 past each hour, `monthly` at 07:00 on the 2nd, Perth time). To build by hand:

```bash
cd generated/sales_performance/dataform
npx @dataform/cli@3 compile             # must be clean
npx @dataform/cli@3 run                 # or start a workflow invocation in the console
```

Order: staging (candidates, rejects, history, current), then `dim_customer` / `dim_product`
(Type 2) and `dim_date`, then `fct_order_line`, then the gold views. Every downstream action
depends on the grain, history and **reject gate** assertions, so a failed blocking check
stops publication instead of publishing wrong numbers.

dbt instead: `dpf generate sales_performance --engine dbt`, then `dbt build` in
`generated/sales_performance--dbt/dbt/` with `--vars` for the policy tag names (Terraform
output `policy_tags`).

## 4. Verify: record evidence for G4

G4 accepts the build only with evidence bound to its **build digest**. Nothing here
fabricates evidence: if a result is missing or belongs to an older build, G4 fails.

```bash
dpf test plan sales_performance                       # every case and what it satisfies
dpf test run sales_performance --live --env test      # automated SQL cases + static checks
dpf test attest sales_performance AT-5 --by "<name>" --role finance
dpf test attest sales_performance AT-8 --by "<name>" --role merchandising
dpf check sales_performance --gate G4
dpf trace sales_performance --print                   # requirement -> ... -> evidence
```

Results go to `evidence/sales_performance/<run>.json` (contract `test-evidence.v1`). Commit
them: they are the acceptance pack.

## 5. Publish and register

Status moves from `provisional` to `published` only when G4 passes.

- The partner listing already exists (Terraform `sharing.tf`). Grant `partner_subscriber`.
- Register in Knowledge Catalog from `generated/sales_performance/catalog-registration.json`
  via the tier 1 MCP server, with the API as fallback. Required aspects: owner, domain,
  classification, SLOs, **grain**, refresh, BRD link, TDD link, signed semantics link.

## 6. Operate

The deployed product checks itself: scheduled freshness and volume queries, Knowledge
Catalog quality scans, and log-based alerts. Each alert links one of the sections below.
To reproduce or record a breach offline:

```bash
dpf monitor sales_performance                                   # observe the deployed product (BigQuery)
dpf monitor sales_performance --evidence run.json --open-change # evaluate a run-evidence.v1 file
```

`--open-change` writes `openspec/changes/monitor-sales-performance-<kind>-<time>/`, a change
with `skip_specs: true` that quotes the breach and links this runbook. It goes through the
gates like any other change.

### Schema drift

Alert `dpf_sales_performance_schema_drift_breaking`: a column was removed or changed type.
The batch went to `raw_<entity>__quarantine`, the watermark did not move, and nothing
downstream changed.

1. Read `changes` in the alert's log entry and agree the change with the source owner.
2. If a type changed, migrate `raw_<entity>` (and the staging body if a column moved).
3. Accept the new schema: `python3 extract_oracle.py <entity> --accept-schema`.
4. The next run re-reads the held rows from the unchanged watermark.

Additive drift (a new column, INT64 widening to NUMERIC) lands normally and is recorded in
`schema_registry`; no action is needed unless the business wants the new column.

### Extract failed

Alert `dpf_sales_performance_extract_failed`: a step failed and the transaction rolled
back, so nothing was committed. Read `stage` and `error` in the log entry, fix the cause
(credentials, network, quota) and re-run; the lookback window re-reads any late rows.
A stalled extractor is also caught by the volume check (OB-3) and, in business hours,
by freshness (OB-1).

### Pipeline failed

Alert `dpf_sales_performance_pipeline_failed`: a scheduled Dataform invocation failed.
Either an action errored or a **blocking** assertion failed and stopped publication.

- **Reject gate** (`assert_stg_order_lines_no_rejects`, R-11): rows failed QR-1 (no
  customer) or QR-2 (negative quantity). They are in `stg_sales.stg_order_lines_rejects`
  with `_reject_reason`. Gold keeps its last good state. Fix the data at the source (the
  next extract lands the correction and staging takes the latest version), then re-run.
  Never delete the assertion to get a refresh through.
- **Grain or history assertion**: a duplicate or overlapping version. Treat as a defect:
  open a change, fix the body or the manifest, and pass G3 before redeploying.
- **Warn-level assertion**: blocks nothing downstream, but Dataform still marks the
  invocation failed, so it raises this alert too. Check which assertion failed before acting.

### Freshness or volume breach

Alert `dpf_sales_performance_monitor_check_failed`: OB-1 (monthly view older than 90
minutes in Perth working hours), OB-2 (partner extract older than 32 days) or OB-3 (order
lines per day outside 16,000–64,000).

1. Check the extractor first (control table `landing_manifest`, latest `ingest_ts`), then
   the Dataform workflow invocations.
2. Freshness measures when the table was last **rebuilt**, not when the source last changed.
   A healthy hourly build over a stalled extract looks fresh; the volume check and the
   `extract_failed` alert cover that case.
3. After the fix, `dpf monitor sales_performance` reports no breach.

## Known limitations, already agreed with the business

Both are in `semantics.md`, so neither should surprise anyone:

1. **Type 2 history starts at go-live.** The source keeps no segment history, so sales
   before go-live carry the segment as at go-live.
2. **Hourly, not continuous.** CDC needs a network route into the database host that does
   not exist yet. See `docs/local-source-connectivity.md`.

## If you later get connectivity

Switching to Datastream CDC is a **TDD-only change**: `capture_mode`, D-10 and
ADR-SALES-002-02. The derived semantics do not change, so the business re-approves
nothing. Compose then selects `extract-rdbms-cdc` instead of `extract-rdbms-watermark`.
Bump the TDD, regenerate, pass G3, redeploy, and record new evidence for G4.
