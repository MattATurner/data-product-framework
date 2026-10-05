-- Typed order lines (one per landed version), carrying customer, date and status from the
-- latest version of the order header. The header is LEFT JOINed: a line whose header has not
-- arrived keeps a NULL customer and is quarantined by QR-1 with a reason, never dropped (R-11).
-- The line's own change time drives deduplication (D-17).
SELECT
  CAST(l.ORDER_ID AS STRING)                                       AS order_id,
  CAST(l.LINE_NO AS INT64)                                         AS order_line_no,
  CAST(o.CUST_ID AS STRING)                                        AS customer_id,
  CAST(l.PROD_ID AS STRING)                                        AS product_id,
  CAST(o.ORDER_DT AS DATE)                                         AS order_date,
  UPPER(CAST(o.STATUS_CD AS STRING))                               AS order_status,
  CAST(l.QTY AS NUMERIC)                                           AS quantity,
  CAST(l.GROSS_AMT AS NUMERIC)                                     AS gross_amount,
  CAST(l.DISCOUNT_AMT AS NUMERIC)                                  AS discount_amount,
  CAST(l.GROSS_AMT AS NUMERIC) - CAST(l.DISCOUNT_AMT AS NUMERIC)   AS net_amount,
  CAST(l.LAST_MODIFIED_TS AS TIMESTAMP)                            AS source_modified_ts,
  l._ingest_ts,
  l._batch_id
FROM {{ ref('raw_order_lines') }} AS l
LEFT JOIN (
  SELECT ORDER_ID, CUST_ID, ORDER_DT, STATUS_CD
  FROM {{ ref('raw_orders') }}
  WHERE TRUE
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ORDER_ID ORDER BY LAST_MODIFIED_TS DESC, _ingest_ts DESC) = 1
) AS o
  ON o.ORDER_ID = l.ORDER_ID
