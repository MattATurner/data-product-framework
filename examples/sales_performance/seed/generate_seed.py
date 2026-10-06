#!/usr/bin/env python3
"""Seed fixtures that exercise the BRD's acceptance scenarios (test data, not pipeline code).

# dpf: role=fixture requirements=R-3,R-4,R-6,R-8,R-11

Each phase is one landing, as the extractor would deliver it. Raw tables are append-only and
staging keeps every landed version (`stg_<entity>_history`), so a Type 2 dimension records
every version that was landed, whether you build between phases or once after both. What it
can never record is a change the source overwrote before an extract saw it: the source keeps
no history. Building between phases mirrors production and exercises the incremental path.

The fixture dates are fixed (March to June 2026) and an incremental run restates only the last
90 days of `fct_order_line` (D-9). Build a seeded environment with a FULL REFRESH, or older
lines never reach the fact.

    python3 generate_seed.py --phase 1 --load   # the world as at end of May
    #   ... run the pipeline with a full refresh (Dataform invocation or `dbt build --full-refresh`) ...
    python3 generate_seed.py --phase 2 --load   # 1 June: re-segmented customer, recategorised product
    #   ... run it again with a full refresh, then record evidence (`dpf test run --live`) ...
    python3 generate_seed.py --phase 3 --load   # a sale with no customer: the reject gate must block
    #   ... run the pipeline: staging quarantines the line and gold does not refresh ...
    python3 generate_seed.py --phase 4 --load   # the source corrects the order's customer
    #   ... run it with a full refresh: the reject view is empty and gold refreshes again ...

    AX-3   a line amended twice counts once, at the later values      (phase 1)
    AX-6   a line cancelled in April is visible but not counted       (phase 1)
    AX-4   customer C-001 is SMB in March, Enterprise from 1 June     (phases 1 + 2)
    AX-7   product P-200 is GADGETS in March, WIDGETS from 1 June     (phases 1 + 2)
    AX-12  order SO-1005 has no customer: quarantined with a reason   (phase 3; corrected in phase 4)

Tables are created with explicit schemas that match what extract_oracle.py derives from
the Oracle cursor (NUMBER(p,0) -> INT64, NUMBER -> NUMERIC, DATE -> DATETIME,
TIMESTAMP -> TIMESTAMP) plus the same lineage columns and `_source_pk_hash` rule.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).parent / "out"
NOW = datetime.now(timezone.utc).isoformat()
LINEAGE = [("_ingest_ts", "TIMESTAMP"), ("_batch_id", "STRING"), ("_source_system", "STRING"),
           ("_op", "STRING"), ("_source_pk_hash", "STRING")]

# entity -> (columns with BigQuery types, natural key)
SCHEMA = {
    "customers": ([("CUST_ID", "STRING"), ("CUST_NAME", "STRING"), ("SEGMENT_CD", "STRING"), ("REGION_CD", "STRING"),
                   ("EMAIL", "STRING"), ("PHONE", "STRING"), ("LAST_MODIFIED_TS", "TIMESTAMP")], ["CUST_ID"]),
    "products": ([("PROD_ID", "STRING"), ("PROD_NAME", "STRING"), ("CATEGORY_CD", "STRING"),
                  ("LAST_MODIFIED_TS", "TIMESTAMP")], ["PROD_ID"]),
    "orders": ([("ORDER_ID", "STRING"), ("CUST_ID", "STRING"), ("ORDER_DT", "DATETIME"), ("STATUS_CD", "STRING"),
                ("LAST_MODIFIED_TS", "TIMESTAMP")], ["ORDER_ID"]),
    "order_lines": ([("ORDER_ID", "STRING"), ("LINE_NO", "INT64"), ("PROD_ID", "STRING"), ("QTY", "NUMERIC"),
                     ("GROSS_AMT", "NUMERIC"), ("DISCOUNT_AMT", "NUMERIC"), ("LAST_MODIFIED_TS", "TIMESTAMP")],
                    ["ORDER_ID", "LINE_NO"]),
}

PHASES = {
    # Phase 1 - the world as at end of May. C-001 is SMB; P-200 is a gadget.
    1: {
        "customers": [
            ("C-001", "Acme Pty Ltd", "SMB", "WA", "ops@acme.example", "+61 8 5550 0001", "2026-03-01 09:00:00"),
            ("C-002", "Borden Group", "ENTERPRISE", "NSW", "ap@borden.example", "+61 2 5550 0002", "2026-01-15 09:00:00"),
            ("C-003", "Corella Co", "SMB", "VIC", "hi@corella.example", "+61 3 5550 0003", "2026-02-02 09:00:00"),
        ],
        "products": [
            ("P-100", "Widget Standard", "WIDGETS", "2026-01-01 00:00:00"),
            ("P-200", "Gadget Pro", "GADGETS", "2026-01-01 00:00:00"),
            ("P-300", "Service Plan", "SERVICES", "2026-01-01 00:00:00"),
        ],
        "orders": [
            ("SO-1001", "C-001", "2026-03-10 00:00:00", "FULFILLED", "2026-03-10 10:00:00"),
            ("SO-1002", "C-002", "2026-03-18 00:00:00", "FULFILLED", "2026-03-18 11:00:00"),
            ("SO-1003", "C-003", "2026-04-05 00:00:00", "CANCELLED", "2026-04-06 09:00:00"),  # AX-6
        ],
        "order_lines": [
            ("SO-1001", 1, "P-100", 10, "1000.00", "100.00", "2026-03-10 10:00:00"),
            # AX-3: the same line amended twice. Only the latest version may count.
            ("SO-1001", 2, "P-200", 5, "750.00", "0.00", "2026-03-10 10:00:00"),
            ("SO-1001", 2, "P-200", 7, "1050.00", "50.00", "2026-03-11 08:30:00"),
            ("SO-1001", 2, "P-200", 6, "900.00", "90.00", "2026-03-12 16:45:00"),
            ("SO-1002", 1, "P-300", 1, "2400.00", "200.00", "2026-03-18 11:00:00"),
            ("SO-1003", 1, "P-100", 20, "2000.00", "0.00", "2026-04-06 09:00:00"),  # cancelled (AX-6)
        ],
    },
    # Phase 2 - 1 June: C-001 re-segmented (AX-4), P-200 recategorised (AX-7), a June sale of both.
    2: {
        "customers": [
            ("C-001", "Acme Pty Ltd", "ENTERPRISE", "WA", "ops@acme.example", "+61 8 5550 0001", "2026-06-01 09:00:00"),
        ],
        "products": [
            ("P-200", "Gadget Pro", "WIDGETS", "2026-06-01 00:00:00"),
        ],
        "orders": [
            ("SO-1004", "C-001", "2026-06-12 00:00:00", "FULFILLED", "2026-06-12 14:00:00"),
        ],
        "order_lines": [
            ("SO-1004", 1, "P-200", 3, "450.00", "0.00", "2026-06-12 14:00:00"),
        ],
    },
    # Phase 3 - a sale whose order names no customer (AX-12): quarantined with a reason, and the
    # blocking reject gate stops every downstream refresh until it is resolved.
    3: {
        "customers": [],
        "products": [],
        "orders": [
            ("SO-1005", None, "2026-06-20 00:00:00", "FULFILLED", "2026-06-20 10:00:00"),
        ],
        "order_lines": [
            ("SO-1005", 1, "P-100", 2, "200.00", "0.00", "2026-06-20 10:00:00"),
        ],
    },
    # Phase 4 - the source corrects SO-1005 (AX-12 recovery): the order header now names its
    # customer. The line is unchanged; staging joins the latest header version, so the line
    # leaves the reject view and the next run publishes again.
    4: {
        "customers": [],
        "products": [],
        "orders": [
            ("SO-1005", "C-002", "2026-06-20 00:00:00", "FULFILLED", "2026-06-20 12:00:00"),
        ],
        "order_lines": [],
    },
}

EXPECT = {
    1: ["AX-3  SO-1001 line 2 appears once: quantity 6, net 810.00",
        "AX-6  SO-1003 is in the fact but excluded from April net sales"],
    2: ["AX-4  dim_customer C-001 has two versions: SMB until 2026-06-01, ENTERPRISE from then;",
        "      SO-1001 (March) reports under SMB, SO-1004 (June) under ENTERPRISE",
        "AX-7  dim_product P-200 has two versions: GADGETS until 2026-06-01, WIDGETS from then;",
        "      SO-1001 line 2 (March) reports under GADGETS, SO-1004 (June) under WIDGETS"],
    3: ["AX-12 stg_order_lines_rejects holds SO-1005 line 1 with reason QR-1 (customer_id is null);",
        "      assert_stg_order_lines_no_rejects fails, so the integration and consumption tables",
        "      keep their previous contents until the order is corrected at source and re-landed"],
    4: ["AX-12 stg_order_lines_rejects is empty and the reject gate passes; after a full refresh",
        "      SO-1005 line 1 is in fct_order_line under C-002 (ENTERPRISE)"],
}


def rows_for(name: str, phase: int) -> list[dict]:
    cols, nk = SCHEMA[name]
    names = [c for c, _ in cols]
    out = []
    for r in PHASES[phase][name]:
        rec = dict(zip(names, r))
        pk = "|".join("" if rec[k] is None else str(rec[k]) for k in nk)
        rec |= {"_ingest_ts": NOW, "_batch_id": f"seed-p{phase}-{name}", "_source_system": "ora_local",
                "_op": "upsert", "_source_pk_hash": hashlib.sha256(pk.encode("utf-8")).hexdigest()}
        out.append(rec)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--phase", type=int, choices=sorted(PHASES), default=1)
    ap.add_argument("--load", action="store_true", help="append the phase to the raw tables in BigQuery")
    ap.add_argument("--project", default="data-product-framework")
    ap.add_argument("--dataset", default="raw_ora_local")
    ap.add_argument("--location", default="us-central1")
    a = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    print(f"phase {a.phase}:")
    for name, (cols, _) in SCHEMA.items():
        recs = rows_for(name, a.phase)
        if not recs:
            continue
        with (OUT / f"p{a.phase}_raw_{name}.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=[c for c, _ in cols + LINEAGE])
            w.writeheader()
            w.writerows(recs)
        print(f"  p{a.phase}_raw_{name}.csv  ({len(recs)} rows)")

    if a.load:
        from google.cloud import bigquery

        bq = bigquery.Client(project=a.project, location=a.location)
        for name, (cols, _) in SCHEMA.items():
            recs = rows_for(name, a.phase)
            if not recs:
                continue
            ref = f"{a.project}.{a.dataset}.raw_{name}"
            schema = [bigquery.SchemaField(c, t) for c, t in cols + LINEAGE]
            job = bq.load_table_from_json(recs, ref, job_config=bigquery.LoadJobConfig(
                schema=schema, write_disposition="WRITE_APPEND",
                time_partitioning=bigquery.TimePartitioning(field="_ingest_ts"),
                clustering_fields=["_source_pk_hash"]))
            job.result()
            print(f"  loaded {job.output_rows} rows -> {ref}")

    print(f"\nwritten to {OUT}\nafter the next pipeline run, expect:")
    for line in EXPECT[a.phase]:
        print(f"  {line}")
    if a.phase < max(PHASES):
        print(f"then: generate_seed.py --phase {a.phase + 1} --load")
    return 0


if __name__ == "__main__":
    sys.exit(main())
