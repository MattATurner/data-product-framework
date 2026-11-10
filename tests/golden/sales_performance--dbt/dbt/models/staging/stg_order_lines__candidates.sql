{{ config(
    materialized='view',
    schema=var('staging_dataset'),
    tags=['hourly', 'monthly']
) }}
-- dpf: model=stg_order_lines layer=staging role=staging skill=transform-raw-to-staging satisfies=R-3,R-11 implements=conform-staging part=candidates
WITH typed AS (
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
  FROM {{ source('pg_local', 'raw_order_lines') }} AS l
  LEFT JOIN (
    SELECT order_id, cust_id, order_dt, status_cd
    FROM {{ source('pg_local', 'raw_orders') }}
    WHERE TRUE
    QUALIFY ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY last_modified_ts DESC, _ingest_ts DESC) = 1
  ) AS o
    ON o.order_id = l.order_id
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
