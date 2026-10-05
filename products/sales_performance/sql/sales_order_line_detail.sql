-- Every order line, cancelled ones included and flagged, with the segment, region and
-- category that applied on the sale date (D-16). counted_net_amount is zero for cancelled
-- lines so a drill-down sums to the monthly figure without consumer-side filtering.
-- Contact details are deliberately not exposed (D-13, R-12).
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
