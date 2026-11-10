-- Transactional PostgreSQL 16 schema for the on-premises Sales ERP simulator (pg_local).
-- Permissive open-source PostgreSQL; runs identically in Docker (postgres:16-alpine) or GCE COS.

CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE IF NOT EXISTS sales.customers (
  cust_id          TEXT PRIMARY KEY,
  cust_name        TEXT NOT NULL,
  segment_cd       TEXT NOT NULL,
  region_cd        TEXT NOT NULL,
  email            TEXT,
  phone            TEXT,
  last_modified_ts TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sales.products (
  prod_id          TEXT PRIMARY KEY,
  prod_name        TEXT NOT NULL,
  category_cd      TEXT NOT NULL,
  last_modified_ts TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Legacy ERP reality: cust_id is nullable on draft/API order imports, which is why
-- Step 4's malformed order (SO-1005) can commit in OLTP and must be caught by DPF QR-1.
CREATE TABLE IF NOT EXISTS sales.orders (
  order_id         TEXT PRIMARY KEY,
  cust_id          TEXT,
  order_dt         TIMESTAMP NOT NULL,
  status_cd        TEXT NOT NULL,
  last_modified_ts TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sales.order_lines (
  order_id         TEXT NOT NULL REFERENCES sales.orders(order_id) ON DELETE CASCADE,
  line_no          INTEGER NOT NULL,
  prod_id          TEXT NOT NULL,
  qty              NUMERIC(12, 2) NOT NULL,
  gross_amt        NUMERIC(12, 2) NOT NULL,
  discount_amt     NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
  last_modified_ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (order_id, line_no)
);

CREATE INDEX IF NOT EXISTS idx_customers_mod_ts   ON sales.customers (last_modified_ts);
CREATE INDEX IF NOT EXISTS idx_products_mod_ts    ON sales.products (last_modified_ts);
CREATE INDEX IF NOT EXISTS idx_orders_mod_ts      ON sales.orders (last_modified_ts);
CREATE INDEX IF NOT EXISTS idx_order_lines_mod_ts ON sales.order_lines (last_modified_ts);
