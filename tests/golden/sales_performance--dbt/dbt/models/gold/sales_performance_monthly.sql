{{ config(
    materialized='table',
    schema=var('gold_dataset'),
    tags=['hourly'],
    persist_docs={'relation': true, 'columns': true}
) }}
-- dpf: model=sales_performance_monthly layer=gold role=business_view skill=direct/model-business-view satisfies=R-1,R-4,R-7,R-8
SELECT
  d.year_month,
  c.customer_segment,
  p.product_category,
  c.region,
  SUM(f.net_amount) AS net_sales,
  SUM(f.quantity)   AS units_sold,
  COUNT(*)          AS order_line_count
FROM {{ ref('fct_order_line') }} AS f
JOIN {{ ref('dim_date') }}     AS d ON d.date_key = f.date_key
JOIN {{ ref('dim_customer') }} AS c ON c.sk_customer = f.sk_customer
JOIN {{ ref('dim_product') }}  AS p ON p.sk_product = f.sk_product
WHERE NOT f.is_cancelled
GROUP BY d.year_month, c.customer_segment, p.product_category, c.region
