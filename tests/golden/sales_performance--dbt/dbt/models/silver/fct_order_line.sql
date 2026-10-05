{{ config(
    materialized='incremental',
    schema=var('silver_dataset'),
    tags=['hourly', 'monthly'],
    incremental_strategy='merge',
    unique_key=['order_id', 'order_line_no'],
    partition_by={'field': 'order_date', 'data_type': 'date'},
    cluster_by=['sk_customer', 'sk_product'],
    incremental_predicates=["DBT_INTERNAL_DEST.order_date >= DATE_SUB(CURRENT_DATE('Australia/Perth'), INTERVAL 90 DAY)"],
    persist_docs={'relation': true, 'columns': true}
) }}
-- dpf: model=fct_order_line layer=silver role=fact skill=kimball/model-transaction-fact satisfies=R-2,R-3,R-7,R-8,R-9
WITH source_rows AS (
  SELECT
    *,
    (order_status = 'CANCELLED') AS is_cancelled
  FROM {{ ref('stg_order_lines') }}
  {% if is_incremental() %}WHERE order_date >= DATE_SUB(CURRENT_DATE('Australia/Perth'), INTERVAL 90 DAY){% endif %}
)
SELECT
  s.order_id,
  s.order_line_no,
  s.customer_id,
  COALESCE(d1.sk_customer, -1) AS sk_customer,
  s.product_id,
  COALESCE(d2.sk_product, -1) AS sk_product,
  CAST(FORMAT_DATE('%Y%m%d', s.order_date) AS INT64) AS date_key,
  s.order_date,
  s.quantity,
  s.gross_amount,
  s.discount_amount,
  s.net_amount,
  s.order_status,
  s.source_modified_ts,
  s.is_cancelled
FROM source_rows AS s
LEFT JOIN {{ ref('dim_customer') }} AS d1
  ON d1.customer_id = s.customer_id
 AND TIMESTAMP(s.order_date, 'Australia/Perth') >= d1.valid_from
 AND TIMESTAMP(s.order_date, 'Australia/Perth') < d1.valid_to
LEFT JOIN {{ ref('dim_product') }} AS d2
  ON d2.product_id = s.product_id
 AND TIMESTAMP(s.order_date, 'Australia/Perth') >= d2.valid_from
 AND TIMESTAMP(s.order_date, 'Australia/Perth') < d2.valid_to
