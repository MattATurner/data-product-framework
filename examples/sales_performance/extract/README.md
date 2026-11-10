# PostgreSQL watermark extract

`extract_postgres.py` appends changed rows from the on-premises PostgreSQL source (`pg_local`) to
BigQuery `raw_pg_local.raw_<entity>` every 15 minutes (TDD D-10, BRD R-10). It implements skill
`extract-rdbms-watermark` as bespoke code (tool tier 5). **ADR-015** records why: Google
Cloud has no inbound route to the database, so managed pull tools (Datastream) cannot reach it.
The script runs beside the database and makes outbound HTTPS calls only.

## Delivery semantics

- Predicate: `watermark_column > last watermark - lookback_minutes` (default 15), so rows
  from transactions that commit late are read again, not lost.
- **At-least-once** landing in raw (the lookback re-reads rows); **exactly-once** after
  staging dedupe on natural key + source change timestamp.
- Each batch loads into `raw_<entity>__load_<batch>` (explicit schema, 24 h expiry). Then
  ONE transaction inserts raw rows, watermark and manifest, with row counts checked by
  `ASSERT` before `COMMIT`. A failed run commits nothing; the next run re-reads the window.
- Watermarks keep microsecond precision (ISO 8601, UTC). Session `TIME ZONE` is pinned to `UTC`
  so `TIMESTAMPTZ` and `TIMESTAMP` columns resolve deterministically.

## Schema drift

Types come from the PostgreSQL cursor, never autodetect. Each batch is compared with the last
accepted schema in `schema_registry` (or, if that is empty, with the existing raw table).

| Drift | Example | What happens |
|---|---|---|
| additive | new column; INT64 to NUMERIC/BIGNUMERIC | Raw table evolves, batch lands, schema recorded, INFO `schema_drift_additive` |
| breaking | removed column; other type change | Rows go to `raw_<entity>__quarantine` (lineage + JSON payload), watermark held, alert, exit 1 |

To resolve breaking drift: agree the change, migrate `raw_<entity>` if a type changed, then
run `extract_postgres.py <entity> --accept-schema`. The next run re-reads the held rows.

## Control tables (`dpf_control`, created if missing)

- `extract_watermark`: one row per committed batch; `MAX(watermark_high)` is the watermark.
- `landing_manifest`: one `landing-manifest.v1` per batch (key columns, `status`, full JSON).
- `schema_registry`: accepted schema per entity; the latest `recorded_at` wins.

## Run

```bash
# PostgreSQL 16 (Docker, GCE appliance, or any PostgreSQL DSN):
pip install "psycopg[binary]" google-cloud-bigquery pyyaml jsonschema
export PGUSER=sales_app PGPASSWORD=sales_demo_pw
python3 extract_postgres.py --dry-run           # reads PostgreSQL only; prints manifests
python3 extract_postgres.py [entity] [--config path/to/config.yaml]

# Zero-Docker follow-along mode (uses Python stdlib sqlite3 in WAL mode):
python3 extract_postgres.py --dsn sqlite:///../postgres-sim/sales_erp.sqlite --dry-run
```

Outside this repository, set `DPF_CONTRACTS_DIR` so manifests are checked against the contract.

## Alerts

Logs are single-line JSON on stdout (Cloud Logging reads `severity` and `message`). ERROR
lines carry `dpf_alert`. The generated Terraform (`monitoring.tf`) turns each into a
log-based metric named `dpf_<product>_<alert>` with an alert policy that links the runbook:

| `dpf_alert` | Meaning | Fields | Metric | Runbook |
|---|---|---|---|---|
| `schema_drift_breaking` | a batch was quarantined, watermark held | `source_system`, `entity`, `batch_id`, `changes` | `dpf_sales_performance_schema_drift_breaking` | [`#schema-drift`](../RUNBOOK.md#schema-drift) |
| `extract_failed` | a step failed and nothing was committed | `stage`, `error` | `dpf_sales_performance_extract_failed` | [`#extract-failed`](../RUNBOOK.md#extract-failed) |

Exit codes: 0 success or no new rows; 1 any failure or breaking drift; 2 config or usage error.
