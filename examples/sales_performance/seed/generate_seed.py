#!/usr/bin/env python3
"""Seed fixtures that prove the BRD's acceptance examples.

The data is chosen so each acceptance example has a case to exercise. Run the
pipeline over this and every AX- reference in the BRD has evidence.

    python3 generate_seed.py --phase 1 --load   # initial load, state as at May
    #   ... run the Dataform pipeline ...
    python3 generate_seed.py --phase 2 --load   # later load: the segment change + June order
    #   ... run the Dataform pipeline again ...

Two phases matter. A Type 2 dimension accumulates history as changes ARRIVE; loading
both states at once lets staging collapse them and the earlier segment is never seen.
This mirrors production, where the June change simply turns up in a later run.

    AX-3  a line amended twice counts once, at the later values     (phase 1)
    AX-4  a customer SMB in March, Enterprise in June               (needs both phases)
    AX-6  a line cancelled in April is visible but not counted      (phase 1)
"""
from __future__ import annotations

import argparse, csv, hashlib, sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).parent / "out"
NOW = datetime.now(timezone.utc).isoformat()

# Phase 1 - the world as at end of May. C-001 is still SMB.
CUSTOMERS_P1 = [
    ("C-001", "Acme Pty Ltd",   "SMB",        "WA",  "ops@acme.example",  "+61 8 5550 0001", "2026-03-01 09:00:00"),
    ("C-002", "Borden Group",   "ENTERPRISE", "NSW", "ap@borden.example", "+61 2 5550 0002", "2026-01-15 09:00:00"),
    ("C-003", "Corella Co",     "SMB",        "VIC", "hi@corella.example","+61 3 5550 0003", "2026-02-02 09:00:00"),
]

# Phase 2 - C-001 is re-segmented on 1 June. The dimension closes the SMB row
# AT THAT SOURCE TIMESTAMP, so March sales keep SMB and June sales get ENTERPRISE.
CUSTOMERS_P2 = [
    ("C-001", "Acme Pty Ltd",   "ENTERPRISE", "WA",  "ops@acme.example",  "+61 8 5550 0001", "2026-06-01 09:00:00"),
]

PRODUCTS = [
    ("P-100", "Widget Standard", "WIDGETS",     "2026-01-01 00:00:00"),
    ("P-200", "Gadget Pro",      "GADGETS",     "2026-01-01 00:00:00"),
    ("P-300", "Service Plan",    "SERVICES",    "2026-01-01 00:00:00"),
]

# order_id, cust_id, order_dt, status, last_modified
ORDERS_P1 = [
    ("SO-1001", "C-001", "2026-03-10", "FULFILLED", "2026-03-10 10:00:00"),
    ("SO-1002", "C-002", "2026-03-18", "FULFILLED", "2026-03-18 11:00:00"),
    ("SO-1003", "C-003", "2026-04-05", "CANCELLED", "2026-04-06 09:00:00"),  # AX-6
]
ORDERS_P2 = [
    ("SO-1004", "C-001", "2026-06-12", "FULFILLED", "2026-06-12 14:00:00"),  # AX-4
]

# order_id, line_no, prod_id, qty, gross, discount, last_modified
ORDER_LINES_P1 = [
    ("SO-1001", 1, "P-100",  10, "1000.00", "100.00", "2026-03-10 10:00:00"),
    # AX-3: the same line amended twice. Only the latest may count.
    ("SO-1001", 2, "P-200",   5,  "750.00",   "0.00", "2026-03-10 10:00:00"),
    ("SO-1001", 2, "P-200",   7, "1050.00",  "50.00", "2026-03-11 08:30:00"),
    ("SO-1001", 2, "P-200",   6,  "900.00",  "90.00", "2026-03-12 16:45:00"),
    ("SO-1002", 1, "P-300",   1, "2400.00", "200.00", "2026-03-18 11:00:00"),
    ("SO-1003", 1, "P-100",  20, "2000.00",   "0.00", "2026-04-06 09:00:00"),  # cancelled
]
ORDER_LINES_P2 = [
    ("SO-1004", 1, "P-200",   3,  "450.00",   "0.00", "2026-06-12 14:00:00"),
]

SCHEMA = {
    "customers":   (["CUST_ID","CUST_NAME","SEGMENT_CD","REGION_CD","EMAIL","PHONE","LAST_MODIFIED_TS"], ["CUST_ID"]),
    "products":    (["PROD_ID","PROD_NAME","CATEGORY_CD","LAST_MODIFIED_TS"],                            ["PROD_ID"]),
    "orders":      (["ORDER_ID","CUST_ID","ORDER_DT","STATUS_CD","LAST_MODIFIED_TS"],                    ["ORDER_ID"]),
    "order_lines": (["ORDER_ID","LINE_NO","PROD_ID","QTY","GROSS_AMT","DISCOUNT_AMT","LAST_MODIFIED_TS"],["ORDER_ID","LINE_NO"]),
}

PHASES = {
    1: {"customers": CUSTOMERS_P1, "products": PRODUCTS,
        "orders": ORDERS_P1, "order_lines": ORDER_LINES_P1},
    2: {"customers": CUSTOMERS_P2, "products": [],
        "orders": ORDERS_P2, "order_lines": ORDER_LINES_P2},
}

LINEAGE = ["_ingest_ts","_batch_id","_source_system","_op","_source_pk_hash"]


def rows_for(name, phase):
    cols, nk = SCHEMA[name]
    data = PHASES[phase][name]
    idx = {c: i for i, c in enumerate(cols)}
    for r in data:
        pk = "|".join(str(r[idx[k]]) for k in nk)
        yield dict(zip(cols, r)) | {
            "_ingest_ts": NOW, "_batch_id": f"seed-p{phase}-{name}",
            "_source_system": "ora_local", "_op": "upsert",
            "_source_pk_hash": hashlib.sha256(pk.encode()).hexdigest()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", type=int, choices=[1, 2], default=1)
    ap.add_argument("--load", action="store_true", help="load into BigQuery")
    ap.add_argument("--project", default="data-product-framework")
    ap.add_argument("--dataset", default="raw_ora_local")
    a = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    print(f"phase {a.phase}:")
    for name in SCHEMA:
        recs = list(rows_for(name, a.phase))
        if not recs:
            continue
        with (OUT / f"p{a.phase}_raw_{name}.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=SCHEMA[name][0] + LINEAGE)
            w.writeheader(); w.writerows(recs)
        print(f"  p{a.phase}_raw_{name}.csv  ({len(recs)} rows)")

    if a.load:
        from google.cloud import bigquery
        bq = bigquery.Client(project=a.project, location="us-central1")
        for name in SCHEMA:
            recs = list(rows_for(name, a.phase))
            if not recs:
                continue
            ref = f"{a.project}.{a.dataset}.raw_{name}"
            job = bq.load_table_from_json(recs, ref,
                job_config=bigquery.LoadJobConfig(
                    write_disposition="WRITE_APPEND", autodetect=True))
            job.result()
            print(f"  loaded {job.output_rows} rows -> {ref}")

    print(f"\nwritten to {OUT}")
    if a.phase == 1:
        print("now run the Dataform pipeline, then: generate_seed.py --phase 2 --load")
        print("  AX-3  SO-1001 line 2 appears once, qty 6, net 810.00")
        print("  AX-6  SO-1003 in the fact, excluded from April net sales")
    else:
        print("now re-run the Dataform pipeline. Expected:")
        print("  AX-4  dim_customer C-001 has TWO rows -")
        print("        SMB       valid 1900-01-01 -> 2026-06-01")
        print("        ENTERPRISE valid 2026-06-01 -> 9999-12-31")
        print("        SO-1001 (Mar) -> SMB ; SO-1004 (Jun) -> ENTERPRISE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
