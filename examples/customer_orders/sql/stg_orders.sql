-- Typed order headers (one per landed version) from the object-store drop.
SELECT
  CAST(order_id AS STRING)            AS order_id,
  CAST(customer_id AS STRING)         AS customer_id,
  CAST(order_date AS DATE)            AS order_date,
  UPPER(CAST(status AS STRING))       AS order_status,
  CAST(last_modified_ts AS TIMESTAMP) AS source_modified_ts,
  _ingest_ts,
  _batch_id
FROM {{ ref('raw_orders') }}
