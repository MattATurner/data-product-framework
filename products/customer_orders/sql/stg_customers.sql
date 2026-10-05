-- Typed customers (one per landed version). Current details only (R-5).
SELECT
  CAST(customer_id AS STRING)         AS customer_id,
  CAST(customer_name AS STRING)       AS customer_name,
  CAST(address AS STRING)             AS customer_address,
  CAST(last_modified_ts AS TIMESTAMP) AS source_modified_ts,
  _ingest_ts,
  _batch_id
FROM {{ ref('raw_customers') }}
