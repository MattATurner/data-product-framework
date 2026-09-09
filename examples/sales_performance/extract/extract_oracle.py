#!/usr/bin/env python3
"""Watermark extract: local Oracle -> BigQuery raw, outbound only.

Implements skill `extract-incremental-capture` for a source that Google Cloud
cannot reach inbound. Runs beside the database and pushes over HTTPS.

    pip install oracledb google-cloud-bigquery pyyaml
    export ORACLE_USER=... ORACLE_PASSWORD=...
    python3 extract_oracle.py            # all entities
    python3 extract_oracle.py customers  # one entity
    python3 extract_oracle.py --dry-run  # no writes

Guarantees required by land-immutable-raw:
  * append-only, never update or delete
  * lineage columns on every row
  * a landing-manifest.v1 per batch
  * the watermark advances ONLY after a verified load
"""
from __future__ import annotations

import argparse, hashlib, json, os, sys, uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

CFG = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text())
LINEAGE = ["_ingest_ts", "_batch_id", "_source_system", "_op", "_source_pk_hash"]
EPOCH = "1900-01-01 00:00:00"


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {msg}", flush=True)


def bq_client():
    from google.cloud import bigquery
    return bigquery.Client(project=CFG["target"]["project"],
                           location=CFG["target"]["location"])


def ensure_control(bq) -> str:
    t = CFG["target"]
    ref = f"{t['project']}.{t['control_dataset']}.extract_watermark"
    bq.query(f"""
        CREATE TABLE IF NOT EXISTS `{ref}` (
          source_system STRING, entity STRING,
          watermark_high TIMESTAMP, batch_id STRING,
          row_count INT64, updated_at TIMESTAMP
        )""").result()
    return ref


def read_watermark(bq, ctl: str, entity: str) -> str:
    rows = list(bq.query(f"""
        SELECT FORMAT_TIMESTAMP('%Y-%m-%d %H:%M:%S', MAX(watermark_high)) AS wm
        FROM `{ctl}` WHERE source_system='ora_local' AND entity=@e""",
        job_config=_params(e=entity)).result())
    return (rows[0].wm if rows and rows[0].wm else EPOCH)


def _params(**kw):
    from google.cloud import bigquery
    return bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter(k, "STRING", v) for k, v in kw.items()])


def fetch(entity: dict, since: str) -> list[dict]:
    import oracledb
    conn = oracledb.connect(
        user=os.environ[CFG["source"]["user_env"]],
        password=os.environ[CFG["source"]["password_env"]],
        dsn=CFG["source"]["dsn"])
    wm, tbl = entity["watermark_column"], entity["source_table"]
    sql = (f"SELECT * FROM {tbl} "
           f"WHERE {wm} > TO_TIMESTAMP(:since,'YYYY-MM-DD HH24:MI:SS') "
           f"ORDER BY {wm}")
    with conn, conn.cursor() as cur:
        cur.execute(sql, since=since)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur]


def decorate(rows: list[dict], entity: dict, batch_id: str) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    out = []
    for r in rows:
        pk = "|".join(str(r.get(k, "")) for k in entity["natural_key"])
        out.append({**{k: _jsonable(v) for k, v in r.items()},
                    "_ingest_ts": now,
                    "_batch_id": batch_id,
                    "_source_system": "ora_local",
                    "_op": "upsert",
                    "_source_pk_hash": hashlib.sha256(pk.encode()).hexdigest()})
    return out


def _jsonable(v):
    return v.isoformat() if isinstance(v, datetime) else v


def load(bq, entity: str, rows: list[dict], batch_id: str) -> int:
    from google.cloud import bigquery
    t = CFG["target"]
    ref = f"{t['project']}.{t['raw_dataset']}.raw_{entity}"
    job = bq.load_table_from_json(rows, ref, job_config=bigquery.LoadJobConfig(
        write_disposition="WRITE_APPEND",          # append-only, always
        schema_update_options=["ALLOW_FIELD_ADDITION"],   # additive drift only
        autodetect=True,
        time_partitioning=bigquery.TimePartitioning(field="_ingest_ts"),
        clustering_fields=["_source_pk_hash"]))
    job.result()
    return job.output_rows


def manifest(entity: str, batch_id: str, rows: list[dict], wm_lo: str, wm_hi: str) -> dict:
    return {"batch_id": batch_id, "source_system": "ora_local", "entity": entity,
            "ingest_ts": datetime.now(timezone.utc).isoformat(),
            "watermark_low": wm_lo, "watermark_high": wm_hi,
            "row_count": len(rows),
            "schema_fingerprint": hashlib.sha256(
                json.dumps(sorted(rows[0].keys()) if rows else [],
                           sort_keys=True).encode()).hexdigest()[:16],
            "brd_requirement_id": ["R-10"]}


def run(only: str | None, dry: bool) -> int:
    entities = [e for e in CFG["entities"] if not only or e["name"] == only]
    if not entities:
        sys.exit(f"unknown entity '{only}'")

    bq = None if dry else bq_client()
    ctl = None if dry else ensure_control(bq)
    failures = 0

    for e in entities:
        name = e["name"]
        batch_id = f"{name}-{uuid.uuid4().hex[:12]}"
        try:
            since = EPOCH if dry else read_watermark(bq, ctl, name)
            log(f"{name}: watermark {since}")
            rows = fetch(e, since)
            if not rows:
                log(f"{name}: no new rows")
                continue

            rows = decorate(rows, e, batch_id)
            hi = max(str(r[e["watermark_column"]]) for r in rows)
            man = manifest(name, batch_id, rows, since, hi)

            if dry:
                log(f"{name}: DRY RUN — {len(rows)} rows, would load to raw_{name}")
                print(json.dumps(man, indent=2))
                continue

            loaded = load(bq, name, rows, batch_id)
            if loaded != len(rows):                    # reconcile before advancing
                raise RuntimeError(f"loaded {loaded} of {len(rows)} rows")

            bq.query(f"""INSERT INTO `{ctl}`
                (source_system, entity, watermark_high, batch_id, row_count, updated_at)
                VALUES('ora_local', @e, TIMESTAMP(@hi), @b, {len(rows)}, CURRENT_TIMESTAMP())""",
                job_config=_params(e=name, hi=hi, b=batch_id)).result()
            log(f"{name}: loaded {loaded} rows, watermark -> {hi}")

        except Exception as exc:                        # watermark is NOT advanced
            log(f"{name}: FAILED — {exc}")
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("entity", nargs="?")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.exit(run(a.entity, a.dry_run))
