-- Typed order lines (one per landed version), carrying customer, date and status from the
-- latest version of the order header. The header is LEFT JOINed: a line whose header has not
-- arrived keeps a NULL customer and is quarantined by QR-1 with a reason, never dropped (R-11).
-- The line's own change time drives deduplication (D-17).
SELECT
  CAST(l.order_id AS STRING)                                       AS order_id,
  CAST(l.line_no AS INT64)                                         AS order_line_no,
  CAST(o.cust_id AS STRING)                                        AS customer_id,
  CAST(l.prod_id AS STRING)                                        AS product_id,
  CAST(o.order_dt AS DATE)                                         AS order_date,
  UPPER(CAST(o.status_cd AS STRING))                               AS order_status,
  CAST(l.qty AS NUMERIC)                                           AS quantity,
  CAST(l.gross_amt AS NUMERIC)                                     AS gross_amount,
  CAST(l.discount_amt AS NUMERIC)                                  AS discount_amount,
  CAST(l.gross_amt AS NUMERIC) - CAST(l.discount_amt AS NUMERIC)   AS net_amount,
  CAST(l.last_modified_ts AS TIMESTAMP)                            AS source_modified_ts,
  l._ingest_ts,
  l._batch_id
FROM {{ ref('raw_order_lines') }} AS l
LEFT JOIN (
  SELECT order_id, cust_id, order_dt, status_cd
  FROM {{ ref('raw_orders') }}
  WHERE TRUE
  QUALIFY ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY last_modified_ts DESC, _ingest_ts DESC) = 1
) AS o
  ON o.order_id = l.order_id
