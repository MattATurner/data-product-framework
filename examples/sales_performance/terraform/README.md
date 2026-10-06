# Infrastructure — sales_performance

This directory is a **wrapper**. Every resource comes from the module that `dpf generate`
writes to `generated/sales_performance/terraform/`; this root module only configures the
`google` and `google-beta` providers and passes inputs. To change the infrastructure, change
`products/sales_performance/product.yaml` (or a generator) and regenerate. Never edit the
generated files.

```bash
dpf generate sales_performance                 # writes generated/sales_performance/
cp terraform.tfvars.example terraform.tfvars   # set the groups and the Dataform repository
terraform init
terraform plan
terraform apply
```

Apply it **before the first extract**: it creates the control tables the extractor writes to.

## Before you apply

The example was deployed to a sandbox project to collect real G4 evidence. These are the
prerequisites that deployment needed. The module creates none of them.

| Prerequisite | Needed by |
|---|---|
| APIs: BigQuery, BigQuery Data Transfer, BigQuery Data Policy, BigQuery sharing (`analyticshub.googleapis.com`), Data Catalog, Dataform, Knowledge Catalog (`dataplex.googleapis.com`), Logging, Monitoring | every resource type in the module |
| Service agents: `gcloud beta services identity create --service=<api>` for `dataplex`, `dataform` and `bigquerydatatransfer` | quality scans, workflow invocations, scheduled checks |
| The three groups in `terraform.tfvars` must exist | dataset access, masked reader, fine-grained reader |
| `dataform_service_account`: BigQuery Data Owner and Job User, Data Catalog Viewer, and membership of `contact_reader_group`. The Dataform service agent needs Service Account Token Creator on it | strict act-as checks need a custom service account; setting policy tags needs Data Owner plus Data Catalog Viewer; rebuilding `dim_customer` reads the tagged columns |
| `monitor_service_account`: BigQuery Job User and Data Viewer. The Data Transfer service agent needs Service Account Token Creator on it | the scheduled freshness and volume checks |

The wrapper bills API calls to the product project (`billing_project` with
`user_project_override`). Without that, BigQuery sharing rejects user credentials that have
no quota project.

## Apply twice

The quality scans check that their tables exist, so on a new project the first apply fails on
the two `google_dataplex_datascan` resources. Everything else is created. Apply again after the
first build.

## What the generated module creates

| File | Resources | Traces to |
|---|---|---|
| `datasets.tf` | raw, staging, silver, gold, share, assertions and control datasets | `select-engine-and-storage` |
| `access.tf` | dataset access for the consumer and analyst groups; silver authorises the gold views | R-1, R-2, R-7, R-12 |
| `governance.tf` | taxonomy, `pii_contact` policy tag, null-mask data policy for analysts | R-12 |
| `sharing.tf` | BigQuery sharing exchange, listing over the partner extract, optional subscriber | R-13 |
| `orchestration.tf` | Dataform release configuration plus one workflow configuration per schedule | R-10 (hourly), R-13 (monthly) |
| `monitoring.tf` | freshness and volume checks (scheduled queries), log-based metrics, alert policies | R-10, R-13, `monitor-data-product` |
| `quality.tf` | Knowledge Catalog data quality scans (`google_dataplex_datascan`) | `enforce-data-quality` |
| `control.tf` | `extract_watermark`, `landing_manifest`, `schema_registry` | R-10 |

## Not covered

- **The Dataform repository itself.** `dataform_repository` names an existing repository
  whose default branch holds the generated `dataform/` tree. There is no MCP option yet
  (`registry/mcp_servers.yaml`). Two set-ups work:
  - **Git-connected.** Keep the default `dataform_release_schedule`: the release
    configuration compiles the default branch every hour.
  - **Dataform-hosted** (no Git remote). Strict act-as checks reject automatic release
    there, so set `dataform_release_schedule = ""` and release on every deploy
    (RUNBOOK step 1). The workflow configurations run only the current release.
- **The extractor host.** `extract_oracle.py` runs beside the database (ADR-015); see
  `../extract/README.md`.
