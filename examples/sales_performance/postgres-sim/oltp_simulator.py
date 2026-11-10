#!/usr/bin/env python3
# dpf: role=fixture requirements=R-3,R-4,R-6,R-8,R-10,R-11
"""Transactional OLTP Order Simulator for the Sales ERP PostgreSQL 16 showcase (pg_local).

Drives real INSERT, UPDATE, and ALTER TABLE transactions against PostgreSQL 16 (or zero-Docker
SQLite WAL) across 5 deterministic showcase story beats OR continuous 15-minute live traffic:

  step 1a / 1b / 1c (or `step 1` with callback):
      Baseline trading + 2 real in-place OLTP amendments to SO-1001 line 2 + cancelled SO-1003.
  step 2:
      Mid-quarter reclassification: UPDATEs C-001 (SMB -> ENTERPRISE) and P-200 (GADGETS -> WIDGETS)
      in place in PostgreSQL (overwriting prior values!) + inserts June order SO-1004.
  step 3:
      Late-committing transaction: commits order SO-1004B with last_modified_ts 6 minutes BEHIND
      the previous high-watermark (rescued by extract_postgres.py's 15-minute lookback window).
  step 4:
      Poison-pill bad order: INSERTs SO-1005 with cust_id = NULL -> quarantined by QR-1 in
      stg_order_lines_rejects and blocks gold publication.
  step 5:
      Source remediation: UPDATEs SO-1005 to set cust_id = 'C-002' -> clears _rejects and
      unblocks gold refresh.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import random
import re
import sys
import time

HERE = Path(__file__).resolve().parent
SCHEMA_SQL = HERE / "schema.sql"
UTC = timezone.utc


class DBAdapter:
    """Uniform SQL execution wrapper across PostgreSQL (psycopg) and SQLite WAL."""

    def __init__(self, dsn: str, user: str | None = None, password: str | None = None):
        self.dsn = dsn
        self.is_sqlite = dsn.startswith("sqlite:")
        if self.is_sqlite:
            import sqlite3
            db_path = re.sub(r"^sqlite:(?:///)?", "", dsn) or ":memory:"
            if dsn.startswith("sqlite:////"):
                db_path = "/" + db_path.lstrip("/")
            self.conn = sqlite3.connect(db_path)
            self.conn.execute("PRAGMA journal_mode=WAL")
        else:
            try:
                import psycopg
                self.conn = psycopg.connect(dsn, user=user, password=password, autocommit=False)
            except ImportError:
                import psycopg2
                self.conn = psycopg2.connect(dsn, user=user, password=password)
            with self.conn.cursor() as cur:
                cur.execute("SET TIME ZONE 'UTC'")
            self.conn.commit()

    def _rewrite(self, sql: str) -> str:
        if not self.is_sqlite:
            return sql
        s = re.sub(r"\bsales\.", "", sql)
        return s.replace("%s", "?")

    def exec(self, sql: str, params: tuple = ()) -> None:
        q = self._rewrite(sql)
        if self.is_sqlite:
            self.conn.execute(q, params)
        else:
            with self.conn.cursor() as cur:
                cur.execute(q, params)

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        q = self._rewrite(sql)
        if self.is_sqlite:
            cur = self.conn.execute(q, params)
            return cur.fetchall()
        with self.conn.cursor() as cur:
            cur.execute(q, params)
            return list(cur.fetchall())

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


def init_schema(db: DBAdapter) -> None:
    if db.is_sqlite:
        stmts = [
            """CREATE TABLE IF NOT EXISTS customers (
                 cust_id TEXT PRIMARY KEY, cust_name TEXT NOT NULL, segment_cd TEXT NOT NULL,
                 region_cd TEXT NOT NULL, email TEXT, phone TEXT, last_modified_ts TIMESTAMPTZ NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS products (
                 prod_id TEXT PRIMARY KEY, prod_name TEXT NOT NULL, category_cd TEXT NOT NULL,
                 last_modified_ts TIMESTAMPTZ NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS orders (
                 order_id TEXT PRIMARY KEY, cust_id TEXT, order_dt TIMESTAMP NOT NULL,
                 status_cd TEXT NOT NULL, last_modified_ts TIMESTAMPTZ NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS order_lines (
                 order_id TEXT NOT NULL, line_no INTEGER NOT NULL, prod_id TEXT NOT NULL,
                 qty NUMERIC(12, 2) NOT NULL, gross_amt NUMERIC(12, 2) NOT NULL,
                 discount_amt NUMERIC(12, 2) NOT NULL, last_modified_ts TIMESTAMPTZ NOT NULL,
                 PRIMARY KEY (order_id, line_no))""",
        ]
        for s in stmts:
            db.exec(s)
    else:
        raw_sql = SCHEMA_SQL.read_text(encoding="utf-8")
        db.exec(raw_sql)
    db.commit()


def reset_data(db: DBAdapter) -> None:
    init_schema(db)
    for tbl in ("sales.order_lines", "sales.orders", "sales.products", "sales.customers"):
        db.exec(f"DELETE FROM {tbl}")
    db.commit()


def upsert_customer(db: DBAdapter, row: tuple) -> None:
    db.exec(
        """INSERT INTO sales.customers (cust_id, cust_name, segment_cd, region_cd, email, phone, last_modified_ts)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (cust_id) DO UPDATE SET
             cust_name = EXCLUDED.cust_name,
             segment_cd = EXCLUDED.segment_cd,
             region_cd = EXCLUDED.region_cd,
             email = EXCLUDED.email,
             phone = EXCLUDED.phone,
             last_modified_ts = EXCLUDED.last_modified_ts""",
        row,
    )


def upsert_product(db: DBAdapter, row: tuple) -> None:
    db.exec(
        """INSERT INTO sales.products (prod_id, prod_name, category_cd, last_modified_ts)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (prod_id) DO UPDATE SET
             prod_name = EXCLUDED.prod_name,
             category_cd = EXCLUDED.category_cd,
             last_modified_ts = EXCLUDED.last_modified_ts""",
        row,
    )


def upsert_order(db: DBAdapter, row: tuple) -> None:
    db.exec(
        """INSERT INTO sales.orders (order_id, cust_id, order_dt, status_cd, last_modified_ts)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (order_id) DO UPDATE SET
             cust_id = EXCLUDED.cust_id,
             order_dt = EXCLUDED.order_dt,
             status_cd = EXCLUDED.status_cd,
             last_modified_ts = EXCLUDED.last_modified_ts""",
        row,
    )


def upsert_line(db: DBAdapter, row: tuple) -> None:
    db.exec(
        """INSERT INTO sales.order_lines (order_id, line_no, prod_id, qty, gross_amt, discount_amt, last_modified_ts)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (order_id, line_no) DO UPDATE SET
             prod_id = EXCLUDED.prod_id,
             qty = EXCLUDED.qty,
             gross_amt = EXCLUDED.gross_amt,
             discount_amt = EXCLUDED.discount_amt,
             last_modified_ts = EXCLUDED.last_modified_ts""",
        row,
    )


def apply_step(db: DBAdapter, step: str) -> dict:
    init_schema(db)
    if step == "1a":
        for c in [
            ("C-001", "Acme Pty Ltd", "SMB", "WA", "ops@acme.example", "+61 8 5550 0001", "2026-03-01T09:00:00+00:00"),
            ("C-002", "Borden Group", "ENTERPRISE", "NSW", "ap@borden.example", "+61 2 5550 0002", "2026-01-15T09:00:00+00:00"),
            ("C-003", "Corella Co", "SMB", "VIC", "hi@corella.example", "+61 3 5550 0003", "2026-02-02T09:00:00+00:00"),
        ]:
            upsert_customer(db, c)
        for p in [
            ("P-100", "Widget Standard", "WIDGETS", "2026-01-01T00:00:00+00:00"),
            ("P-200", "Gadget Pro", "GADGETS", "2026-01-01T00:00:00+00:00"),
            ("P-300", "Service Plan", "SERVICES", "2026-01-01T00:00:00+00:00"),
        ]:
            upsert_product(db, p)
        upsert_order(db, ("SO-1001", "C-001", "2026-03-10 00:00:00", "FULFILLED", "2026-03-10T10:00:00+00:00"))
        upsert_line(db, ("SO-1001", 1, "P-100", "10", "1000.00", "100.00", "2026-03-10T10:00:00+00:00"))
        upsert_line(db, ("SO-1001", 2, "P-200", "5", "750.00", "0.00", "2026-03-10T10:00:00+00:00"))
        db.commit()
        return {"step": "1a", "summary": "10 Mar: Seeded customers (C-001=SMB), products (P-200=GADGETS), and initial order SO-1001 (line 2 qty=5)."}

    if step == "1b":
        upsert_line(db, ("SO-1001", 2, "P-200", "7", "1050.00", "50.00", "2026-03-11T08:30:00+00:00"))
        db.commit()
        return {"step": "1b", "summary": "11 Mar: Amended SO-1001 line 2 in PostgreSQL (qty 5 -> 7, gross 1050.00, discount 50.00)."}

    if step in ("1c", "1"):
        if step == "1":
            apply_step(db, "1a")
        upsert_line(db, ("SO-1001", 2, "P-200", "6", "900.00", "90.00", "2026-03-12T16:45:00+00:00"))
        upsert_order(db, ("SO-1002", "C-002", "2026-03-18 00:00:00", "FULFILLED", "2026-03-18T11:00:00+00:00"))
        upsert_line(db, ("SO-1002", 1, "P-300", "1", "2400.00", "200.00", "2026-03-18T11:00:00+00:00"))
        upsert_order(db, ("SO-1003", "C-003", "2026-04-05 00:00:00", "CANCELLED", "2026-04-06T09:00:00+00:00"))
        upsert_line(db, ("SO-1003", 1, "P-100", "20", "2000.00", "0.00", "2026-04-06T09:00:00+00:00"))
        db.commit()
        return {"step": step, "summary": "12 Mar - 06 Apr: Final amendment on SO-1001 line 2 (qty -> 6, net -> 810.00) plus SO-1002 and cancelled SO-1003."}

    if step == "2":
        # Overwrites SMB -> ENTERPRISE and GADGETS -> WIDGETS in-place in PostgreSQL!
        db.exec(
            "UPDATE sales.customers SET segment_cd = %s, last_modified_ts = %s WHERE cust_id = %s",
            ("ENTERPRISE", "2026-06-01T09:00:00+00:00", "C-001"),
        )
        db.exec(
            "UPDATE sales.products SET category_cd = %s, last_modified_ts = %s WHERE prod_id = %s",
            ("WIDGETS", "2026-06-01T00:00:00+00:00", "P-200"),
        )
        upsert_order(db, ("SO-1004", "C-001", "2026-06-12 00:00:00", "FULFILLED", "2026-06-12T14:00:00+00:00"))
        upsert_line(db, ("SO-1004", 1, "P-200", "3", "450.00", "0.00", "2026-06-12T14:00:00+00:00"))
        db.commit()
        return {"step": "2", "summary": "Reclassified C-001 -> ENTERPRISE and P-200 -> WIDGETS in-place in PostgreSQL; inserted June order SO-1004."}

    if step == "3":
        # Late-committing OLTP transaction: timestamp is 2026-06-12T13:54:00Z (6 minutes BEHIND
        # SO-1004's 14:00:00Z watermark high, inside lookback_minutes=15 -> 13:45:00Z..14:00:00Z!)
        upsert_order(db, ("SO-1004B", "C-002", "2026-06-12 00:00:00", "FULFILLED", "2026-06-12T13:54:00+00:00"))
        upsert_line(db, ("SO-1004B", 1, "P-300", "2", "1200.00", "100.00", "2026-06-12T13:54:00+00:00"))
        db.commit()
        return {"step": "3", "summary": "Committed delayed OLTP order SO-1004B at 13:54:00Z (6 min behind 14:00:00Z watermark, inside 15-min lookback)."}

    if step == "4":
        # Poison-pill order with NULL cust_id -> triggers QR-1 quarantine and blocks gold refresh!
        upsert_order(db, ("SO-1005", None, "2026-06-20 00:00:00", "FULFILLED", "2026-06-20T10:00:00+00:00"))
        upsert_line(db, ("SO-1005", 1, "P-100", "2", "200.00", "0.00", "2026-06-20T10:00:00+00:00"))
        db.commit()
        return {"step": "4", "summary": "Inserted malformed order SO-1005 (cust_id = NULL) to trigger QR-1 quarantine and halt gold publication."}

    if step == "5":
        # Source ERP fixes SO-1005's customer -> next 15-min extract heals _rejects and unblocks gold!
        db.exec(
            "UPDATE sales.orders SET cust_id = %s, last_modified_ts = %s WHERE order_id = %s",
            ("C-002", "2026-06-20T10:12:00+00:00", "SO-1005"),
        )
        db.commit()
        return {"step": "5", "summary": "Remediated SO-1005 in PostgreSQL (cust_id -> C-002); next 15-min extract clears quarantine."}

    raise ValueError(f"unknown step {step!r} (expected 1, 1a, 1b, 1c, 2, 3, 4, or 5)")


def print_status(db: DBAdapter) -> None:
    init_schema(db)
    counts = {}
    for tbl in ("customers", "products", "orders", "order_lines"):
        counts[tbl] = db.query(f"SELECT COUNT(*) FROM sales.{tbl}")[0][0]
    c1 = db.query("SELECT cust_id, segment_cd, region_cd, last_modified_ts FROM sales.customers WHERE cust_id = %s", ("C-001",))
    p2 = db.query("SELECT prod_id, category_cd, last_modified_ts FROM sales.products WHERE prod_id = %s", ("P-200",))
    so5 = db.query("SELECT order_id, cust_id, status_cd, last_modified_ts FROM sales.orders WHERE order_id = %s", ("SO-1005",))
    print(json.dumps({
        "table_counts": counts,
        "c_001_in_postgres": [str(x) for x in c1[0]] if c1 else None,
        "p_200_in_postgres": [str(x) for x in p2[0]] if p2 else None,
        "so_1005_in_postgres": [str(x) for x in so5[0]] if so5 else None,
    }, indent=2))


def run_live_loop(db: DBAdapter, interval_sec: int, max_ticks: int | None) -> None:
    init_schema(db)
    custs = ["C-001", "C-002", "C-003"]
    prods = [("P-100", 100), ("P-200", 150), ("P-300", 1200)]
    tick = 0
    while max_ticks is None or tick < max_ticks:
        tick += 1
        now = datetime.now(UTC)
        oid = f"SO-LIVE-{now.strftime('%H%M%S')}-{tick:03d}"
        cid = random.choice(custs)
        pid, unit_price = random.choice(prods)
        qty = random.randint(1, 8)
        gross = f"{qty * unit_price:.2f}"
        ts_iso = now.isoformat(timespec="microseconds")
        upsert_order(db, (oid, cid, now.strftime("%Y-%m-%d %H:%M:%S"), "FULFILLED", ts_iso))
        upsert_line(db, (oid, 1, pid, str(qty), gross, "0.00", ts_iso))
        db.commit()
        print(json.dumps({"event": "oltp_order_committed", "order_id": oid, "cust_id": cid,
                          "prod_id": pid, "qty": qty, "gross_amt": gross, "ts": ts_iso}), flush=True)
        if max_ticks is None or tick < max_ticks:
            time.sleep(interval_sec)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PostgreSQL 16 / SQLite WAL OLTP Order Simulator for sales_performance.")
    ap.add_argument("action", choices=["init", "reset", "step", "status", "live"], help="simulator command")
    ap.add_argument("step_id", nargs="?", help="for `step`: 1, 1a, 1b, 1c, 2, 3, 4, or 5")
    ap.add_argument("--dsn", default=os.environ.get("PG_DSN", "host=localhost port=5432 dbname=sales_erp"),
                    help="PostgreSQL DSN or sqlite:///path/to/sales_erp.sqlite")
    ap.add_argument("--interval-sec", type=int, default=30, help="seconds between orders in `live` mode")
    ap.add_argument("--max-ticks", type=int, default=None, help="optional cap on ticks in `live` mode")
    args = ap.parse_args(argv)

    user = os.environ.get("PGUSER", "sales_app")
    password = os.environ.get("PGPASSWORD", "sales_demo_pw")
    db = DBAdapter(args.dsn, user=user, password=password)
    try:
        if args.action == "init":
            init_schema(db)
            print(json.dumps({"status": "ok", "action": "init", "dsn": args.dsn}))
        elif args.action == "reset":
            reset_data(db)
            print(json.dumps({"status": "ok", "action": "reset", "dsn": args.dsn}))
        elif args.action == "status":
            print_status(db)
        elif args.action == "step":
            if not args.step_id:
                ap.error("`step` requires a step_id (1, 1a, 1b, 1c, 2, 3, 4, or 5)")
            res = apply_step(db, args.step_id)
            print(json.dumps({"status": "ok", **res}))
        elif args.action == "live":
            run_live_loop(db, args.interval_sec, args.max_ticks)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
