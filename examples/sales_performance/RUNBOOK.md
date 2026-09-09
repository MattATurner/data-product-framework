# Runbook — sales_performance

Local Oracle to BigQuery in `data-product-framework` / `us-central1`.

| | |
|---|---|
| BRD | `openspec/specs/products/sales/sales_performance/brd/spec.md` (BRD-SALES-002 @ 1.1.0) |
| TDD | `.../tdd/spec.md` (TDD-SALES-002) |
| Signed semantics | `.../semantics.md` |
| Manifest | `products/sales_performance/product.yaml` |

## 0. Verify the specs before building anything

```bash
tools/dpf check sales_performance
```

G0, G1, traceability, engine support and the contract DAG all pass before a line of SQL
runs. If this is red, stop.

## 1. Infrastructure

```bash
cd examples/sales_performance/terraform
terraform init && terraform apply -var project_id=data-product-framework
```

Six datasets in `us-central1`, plus the `pii/contact` policy tag for R-12.

## 2. Data in — pick one

### Option A: seed fixtures (no Oracle needed)

Start here. Proves the whole chain and exercises every acceptance example.

**Load in two phases, running the pipeline between them.** This is not ceremony: a Type 2
dimension accumulates history as changes *arrive*. Loading both states at once lets
staging collapse them and the earlier segment is never recorded — which is exactly the
mistake the two-phase seed exists to prevent.

```bash
cd examples/sales_performance/seed

python3 generate_seed.py --phase 1 --load     # world as at end of May
(cd ../dataform && dataform run)              # build

python3 generate_seed.py --phase 2 --load     # C-001 re-segmented 1 June, plus June order
(cd ../dataform && dataform run)              # rebuild - now history exists
```

After phase 2, `dim_customer` holds two rows for `C-001`:

| segment | valid_from | valid_to |
|---|---|---|
| SMB | 1900-01-01 | 2026-06-01 |
| ENTERPRISE | 2026-06-01 | 9999-12-31 |

The first version opens at a floor date so historical facts resolve to it rather than to
the unknown member. Later versions open at the **source change timestamp**, not load time
— which is what makes AX-4 correct.

### Option B: the real Oracle

```bash
pip install oracledb google-cloud-bigquery pyyaml
export ORACLE_USER=... ORACLE_PASSWORD=...
cd examples/sales_performance/extract
python3 extract_oracle.py --dry-run     # inspect first
python3 extract_oracle.py               # load all entities
```

Outbound only — no inbound route to your workstation is needed. The watermark advances
only after the loaded row count reconciles, so a failed run is safe to repeat.

## 3. Build the models

```bash
cd examples/sales_performance/dataform
dataform compile        # must be clean before running
dataform run
```

Order: staging views, then `dim_customer` / `dim_product` (Type 2) and `dim_date`, then
`fct_order_line`, then `sales_performance_monthly`.

## 4. Verify against the acceptance examples

This is G4. The business signed `semantics.md`; these queries prove it.

```sql
-- AX-3: a line amended twice counts once, at the later values (expect qty 6, net 810.00)
SELECT order_id, order_line_no, quantity, net_amount
FROM `data-product-framework.slv_sales.fct_order_line`
WHERE order_id = 'SO-1001' AND order_line_no = 2;

-- AX-4: March sales stay with SMB even though the customer is now ENTERPRISE
SELECT d.year_month, c.customer_segment, SUM(f.net_amount) AS net_sales
FROM `data-product-framework.slv_sales.fct_order_line` f
JOIN `data-product-framework.slv_sales.dim_date`     d ON d.date_key = f.date_key
JOIN `data-product-framework.slv_sales.dim_customer` c ON c.sk_customer = f.sk_customer
WHERE f.order_id IN ('SO-1001','SO-1004')
GROUP BY 1, 2 ORDER BY 1;

-- AX-6: the cancelled order is visible in the fact...
SELECT order_id, is_cancelled, net_amount
FROM `data-product-framework.slv_sales.fct_order_line`
WHERE order_id = 'SO-1003';

-- ...but excluded from April net sales
SELECT * FROM `data-product-framework.gold_sales.sales_performance_monthly`
WHERE year_month = '2026-04';
```

Assertions must also be green — `assert_fct_order_line_grain` is generated from the
declared grain, so a duplicate fails the build rather than warning.

## 5. Publish and register

Only after step 4 passes does status move from `provisional` to `published`.

- Create the BigQuery sharing listing for the partner extract (R-13).
- Register in Knowledge Catalog via the tier 1 MCP server, with the API as fallback.
  Required aspects: owner, domain, classification, SLOs, **grain**, refresh, BRD link,
  TDD link, signed semantics link.

## Known limitations, already agreed with the business

Both are in `semantics.md`, so neither should surprise anyone:

1. **Type 2 history starts at go-live.** The source keeps no segment history, so sales
   before go-live carry the segment as at go-live.
2. **Hourly, not continuous.** CDC needs a network route into the workstation that does
   not exist yet. See `docs/local-source-connectivity.md`.

## If you later get connectivity

Switching to Datastream CDC is a **TDD-only change** — `capture_mode`, D-10 and
ADR-SALES-002-02. The derived semantics do not change, so the business re-approves
nothing. Bump the TDD, re-run `dpf trace`, redeploy.
