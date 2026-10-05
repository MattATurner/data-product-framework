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

## What the generated module creates

| File | Resources | Traces to |
|---|---|---|
| `datasets.tf` | raw, staging, silver, gold, share, assertions and control datasets | `select-engine-and-storage` |
| `access.tf` | dataset access for the consumer and analyst groups; silver authorises the gold views | R-1, R-2, R-7, R-12 |
| `governance.tf` | taxonomy, `pii/contact` policy tag, null-mask data policy for analysts | R-12 |
| `sharing.tf` | BigQuery sharing exchange, listing over the partner extract, optional subscriber | R-13 |
| `orchestration.tf` | Dataform release configuration plus one workflow configuration per schedule | R-10 (hourly), R-13 (monthly) |
| `monitoring.tf` | freshness and volume checks (scheduled queries), log-based metrics, alert policies | R-10, R-13, `monitor-data-product` |
| `quality.tf` | Knowledge Catalog data quality scans (`google_dataplex_datascan`) | `enforce-data-quality` |
| `control.tf` | `extract_watermark`, `landing_manifest`, `schema_registry` | R-10 |

## Not covered

- **The Dataform repository itself.** `dataform_repository` names an existing repository
  whose default branch holds the generated `dataform/` tree. Create it and connect Git in
  the console or with `gcloud`; there is no MCP option yet (`registry/mcp_servers.yaml`).
- **The extractor host.** `extract_oracle.py` runs beside the database (ADR-015); see
  `../extract/README.md`.
