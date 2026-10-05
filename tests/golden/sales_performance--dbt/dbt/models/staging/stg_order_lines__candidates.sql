{{ config(
    materialized='view',
    schema=var('staging_dataset'),
    tags=['hourly', 'monthly']
) }}
-- dpf: model=stg_order_lines layer=staging role=staging skill=transform-raw-to-staging satisfies=R-3,R-11 implements=conform-staging part=candidates
WITH typed AS (
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
  FROM {{ source('ora_local', 'raw_order_lines') }} AS l
  LEFT JOIN (
    SELECT ORDER_ID, CUST_ID, ORDER_DT, STATUS_CD
    FROM {{ source('ora_local', 'raw_orders') }}
    WHERE TRUE
    QUALIFY ROW_NUMBER() OVER (PARTITION BY ORDER_ID ORDER BY LAST_MODIFIED_TS DESC, _ingest_ts DESC) = 1
  ) AS o
    ON o.ORDER_ID = l.ORDER_ID
)
SELECT
  typed.*,
  ROW_NUMBER() OVER (PARTITION BY order_id, order_line_no ORDER BY source_modified_ts DESC, _ingest_ts DESC) AS _dpf_row_rank,
  ROW_NUMBER() OVER (PARTITION BY order_id, order_line_no, source_modified_ts ORDER BY _ingest_ts DESC) AS _dpf_version_rank,
  CASE
    WHEN customer_id IS NULL THEN 'QR-1'
    WHEN quantity < 0 THEN 'QR-2'
  END AS _reject_reason
FROM typed
