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

This is how the example was deployed to the sandbox project `data-product-framework` on
5 October 2026 to collect G4 evidence.

**Once per project, before the first apply.** The module creates none of these; the table in
`terraform/README.md` says what needs each one.

- Enable the APIs: BigQuery, BigQuery Data Transfer, BigQuery Data Policy, BigQuery sharing,
  Data Catalog, Dataform, Knowledge Catalog, Logging and Monitoring. Granting project roles
  with `gcloud` also needs Cloud Resource Manager.
- Create the service agents: `gcloud beta services identity create --service=<api>` for
  `dataplex.googleapis.com`, `dataform.googleapis.com` and
  `bigquerydatatransfer.googleapis.com`.
- Create the three groups and the two service accounts named in `terraform.tfvars`, with the
  roles listed in `terraform/README.md`.
- Create the Dataform repository named in `dataform_repository`.

```bash
dpf generate sales_performance                 # generated/sales_performance/{dataform,terraform,...}
cd examples/sales_performance/terraform
cp terraform.tfvars.example terraform.tfvars   # groups, repository, service accounts, alert channel
terraform init && terraform apply
```

Seven datasets (raw, staging, silver, gold, share, assertions, control), the control
tables, the `pii_contact` policy tag with a null mask for analysts (R-12), the partner
listing (R-13), orchestration, checks, alerts and Knowledge Catalog quality scans. Apply
before the first extract: the extractor writes to the control tables.

**Apply twice on a new project.** The two quality scans need their tables, so the first
apply fails on them and creates everything else. Run `terraform apply` again after the first
build (step 3).

**Push and release the Dataform code.** Push `generated/sales_performance/dataform/` to the
default branch of the repository. The workflow configurations run only the **current
release**, so a push alone changes nothing that runs.

- **Git-connected repository:** keep the default `dataform_release_schedule`. The release
  configuration compiles the default branch every hour.
- **Dataform-hosted repository** (no Git remote, as in the sandbox): strict act-as checks
  reject automatic release, so set `dataform_release_schedule = ""` and release after every
  push:

```bash
API=https://dataform.googleapis.com/v1beta1
REPO=projects/<project>/locations/us-central1/repositories/<repository>
TOKEN=$(gcloud auth print-access-token)
# 1. Compile the default branch with the release configuration's settings; stop on any error.
COMPILATION=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"releaseConfig\": \"$REPO/releaseConfigs/sales-performance\"}" "$API/$REPO/compilationResults" \
  | python3 -c 'import json,sys; r=json.load(sys.stdin); e=r.get("error") or r.get("compilationErrors"); sys.exit(json.dumps(e)) if e else print(r["name"])') &&
# 2. Make that compilation the current release. The API requires gitCommitish in the body.
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"gitCommitish\": \"main\", \"releaseCompilationResult\": \"$COMPILATION\"}" \
  "$API/$REPO/releaseConfigs/sales-performance?updateMask=releaseCompilationResult"
```

The PATCH prints the release configuration. Without `gitCommitish` it fails with
`git_commitish is not specified`, even though the update mask names only
`releaseCompilationResult`.

## 2. Data in — pick one

### Option A: seed fixtures (no Oracle needed)

Start here. It proves the whole chain and exercises the automated acceptance tests.

**Build with a full refresh.** The fixture dates are fixed (March to June 2026), and an
incremental run restates only the last 90 days of `fct_order_line` (D-9). An incremental
build skips older lines: in the sandbox, SO-1004 (12 June) never reached the fact and AT-4
and AT-7 failed. Dataform: tick "Run with full refresh" (API:
`fullyRefreshIncrementalTablesEnabled`). dbt: `dbt build --full-refresh`.

**Load in phases.** Each phase is one landing, as the extractor would deliver it. Raw is
append-only and staging keeps every landed version (`stg_<entity>_history`), so the Type 2
dimensions get the same history whether you build between phases or once after both.
Building between phases mirrors production. No build can recover a change that the source
overwrote before an extract saw it: the source keeps no history.

```bash
cd examples/sales_performance/seed
python3 generate_seed.py --phase 1 --load   # the world as at end of May
#   build with a full refresh (step 3)
python3 generate_seed.py --phase 2 --load   # 1 June: C-001 re-segmented, P-200 recategorised
#   build again with a full refresh: history now exists
```

After phase 2, `dim_customer` holds two rows for `C-001` (sandbox output):

| customer_segment | valid_from | valid_to |
|---|---|---|
| SMB | 1900-01-01 00:00:00 | 2026-06-01 09:00:00 |
| ENTERPRISE | 2026-06-01 09:00:00 | 9999-12-31 00:00:00 |

The first version opens at a floor date, so historical facts resolve to it rather than to
the unknown member. Later versions open at the **source change timestamp**, not the load
time. That is what makes AX-4 and AX-7 correct.

Phase 3 (`--phase 3`) adds order SO-1005 with no customer. Load it **after** recording
evidence (step 4): the next run quarantines the line and the reject gate stops publication
(AX-12). Phase 4 (`--phase 4`) lands the corrected order, and the next run succeeds again.
With the fixed seed dates, the order reaches gold only on a full refresh, as above.
Section 6, "Pipeline failed", shows what both did in the sandbox.

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
:10 past each hour, `monthly` at 07:00 on the 2nd, Perth time). They run the current
release (step 1), incrementally, as `dataform_service_account`. To build by hand, start a
workflow invocation in the console from the release configuration, with the same service
account (strict act-as checks require it) and, for seeded data, "Run with full refresh". Or
use the CLI:

```bash
cd generated/sales_performance/dataform
npx @dataform/cli@3 compile             # must be clean
npx @dataform/cli@3 run --full-refresh --vars=policy_tag_pii_contact=<terraform output policy_tags>
```

The CLI needs `.df-credentials.json` (`npx @dataform/cli@3 init-creds`). Always pass the
policy tag: with the variable empty, the CLI rebuilds `dim_customer` with no tag on the
contact columns (R-12).

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

In the sandbox, `dpf test run --live` passed all 36 SQL cases and the 5 static cases for
build `sha256:fd95e365e03e…` (`evidence/sales_performance/run-20261005T224325Z.json`). G4
then fails only on the two attestations:

```text
FAIL | acceptance:AT-5 (attestation): no evidence for build sha256:fd95e365e03e… (`dpf test attest sales_performance AT-5 --by <name> --role finance`)
FAIL | acceptance:AT-8 (attestation): no evidence for build sha256:fd95e365e03e… (`dpf test attest sales_performance AT-8 --by <name> --role merchandising`)
     | evidence: 2 missing, 41 passed
```

AT-5 and AT-8 need a person from Finance and from Merchandising to check the figures. Do not
record them for someone else.

## 5. Publish and register

Publishing is a release build like any other, because the status is part of the manifest
and therefore of the build digest. Set `status: published` in
`products/sales_performance/product.yaml`, regenerate (`make golden`) and deploy that build,
then run the automated tests and attestations against it. Grant access and register only
when G4 passes for that digest. dpf never changes the status for you; while the BRD still
carries open assumptions (ADR-009), the generated `data-product.json` reports `provisional`
whatever the manifest says.

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

  Seen in the sandbox: after seed phase 3, an `hourly` invocation ended `FAILED 1, SKIPPED 13,
  SUCCEEDED 30`. The reject gate failed with `Assertion failed, expected zero rows`;
  `fct_order_line`, both gold views and their 10 assertions were skipped, and
  `fct_order_line` kept its earlier rows. The rejects view held SO-1005 line 1 with reason
  `QR-1`. After phase 4 landed the corrected order, the next `hourly` run succeeded (44
  actions), and a full refresh published SO-1005 under C-002.
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

Seed data always breaches OB-3. In the sandbox, `dpf monitor sales_performance` reported:

```text
  ok | OB-1: 2026-10-05T22:45:13+00:00 is outside the business calendar (MON TUE WED THU FRI 08:00-18:00 Australia/Perth); not evaluated
  ok | OB-2: sales_performance_partner_extract is 4 minutes old (limit 46080)
FAIL | volume OB-3: fct_order_line holds 0 rows per P1D (expected 16000–64000)
```

No fixture line is dated yesterday, so the scheduled volume check fails every day and raises
this alert. That is expected for a seeded environment, not an incident.

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
