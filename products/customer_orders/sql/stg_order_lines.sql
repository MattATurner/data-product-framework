-- Typed order lines (one per landed version) from the object-store drop.
SELECT
  CAST(order_id AS STRING)            AS order_id,
  CAST(line_no AS INT64)              AS order_line_no,
  CAST(product_id AS STRING)          AS product_id,
  CAST(quantity AS NUMERIC)           AS quantity,
  CAST(line_amount AS NUMERIC)        AS line_amount,
  CAST(last_modified_ts AS TIMESTAMP) AS source_modified_ts,
  _ingest_ts,
  _batch_id
FROM {{ ref('raw_order_lines') }}
