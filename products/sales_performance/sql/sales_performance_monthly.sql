-- Net sales by month, customer segment, product category and region (D-15).
-- Segment, region and category are the versions that applied on the sale date, resolved in
-- the fact (D-7). Cancelled lines are excluded here, not by the consumer (D-8).
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
