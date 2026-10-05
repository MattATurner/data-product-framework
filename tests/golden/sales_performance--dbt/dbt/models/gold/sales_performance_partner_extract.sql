{{ config(
    materialized='table',
    schema=var('share_dataset'),
    tags=['monthly'],
    persist_docs={'relation': true, 'columns': true}
) }}
-- dpf: model=sales_performance_partner_extract layer=gold role=business_view skill=direct/model-business-view satisfies=R-13
SELECT
  d.year_month,
  p.product_category,
  c.region,
  SUM(f.net_amount) AS net_sales,
  SUM(f.quantity)   AS units_sold
FROM {{ ref('fct_order_line') }} AS f
JOIN {{ ref('dim_date') }}     AS d ON d.date_key = f.date_key
JOIN {{ ref('dim_customer') }} AS c ON c.sk_customer = f.sk_customer
JOIN {{ ref('dim_product') }}  AS p ON p.sk_product = f.sk_product
WHERE NOT f.is_cancelled
  AND f.order_date < DATE_TRUNC(CURRENT_DATE('{{ var('business_timezone') }}'), MONTH)
GROUP BY d.year_month, p.product_category, c.region
