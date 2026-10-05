{{ config(
    materialized='view',
    schema=var('gold_dataset'),
    tags=['hourly']
) }}
-- dpf: model=sales_order_line_detail layer=gold role=business_view skill=direct/model-business-view satisfies=R-2,R-8,R-12
SELECT
  f.order_id,
  f.order_line_no,
  f.order_date,
  d.year_month,
  f.customer_id,
  c.customer_name,
  c.customer_segment,
  c.region,
  f.product_id,
  p.product_name,
  p.product_category,
  f.order_status,
  f.is_cancelled,
  f.quantity,
  f.gross_amount,
  f.discount_amount,
  f.net_amount,
  IF(f.is_cancelled, 0, f.net_amount) AS counted_net_amount
FROM {{ ref('fct_order_line') }} AS f
JOIN {{ ref('dim_date') }}     AS d ON d.date_key = f.date_key
JOIN {{ ref('dim_customer') }} AS c ON c.sk_customer = f.sk_customer
JOIN {{ ref('dim_product') }}  AS p ON p.sk_product = f.sk_product
