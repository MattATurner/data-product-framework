-- One row per customer order with its lines nested (D-3, D-4). Cancelled orders stay visible
-- and carry a zero counted_order_value so totals exclude them in the model (D-6).
-- Customer details are current values (D-5, R-5).
WITH lines AS (
  SELECT
    order_id,
    ARRAY_AGG(STRUCT(order_line_no, product_id, quantity, line_amount) ORDER BY order_line_no) AS order_lines,
    SUM(line_amount) AS order_value,
    COUNT(*)         AS line_count
  FROM {{ ref('stg_order_lines') }}
  GROUP BY order_id
)
SELECT
  o.order_id,
  o.customer_id,
  c.customer_name,
  c.customer_address,
  o.order_date,
  o.order_status,
  o.order_status = 'CANCELLED'                                    AS is_cancelled,
  COALESCE(l.order_value, 0)                                      AS order_value,
  IF(o.order_status = 'CANCELLED', 0, COALESCE(l.order_value, 0)) AS counted_order_value,
  COALESCE(l.line_count, 0)                                       AS line_count,
  l.order_lines
FROM {{ ref('stg_orders') }} AS o
LEFT JOIN lines AS l ON l.order_id = o.order_id
LEFT JOIN {{ ref('stg_customers') }} AS c ON c.customer_id = o.customer_id
