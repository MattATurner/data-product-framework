{{ config(tags=['acceptance']) }}
-- dpf: test=acceptance:AT-9 model=sales_performance_monthly satisfies=R-7 verifies=AX-9
SELECT m.total_net_sales, f.total_net_amount, m.total_lines, f.total_fact_lines
FROM (
  SELECT COALESCE(SUM(net_sales), 0) AS total_net_sales, COALESCE(SUM(order_line_count), 0) AS total_lines
  FROM {{ ref('sales_performance_monthly') }}
) AS m
CROSS JOIN (
  SELECT COALESCE(SUM(net_amount), 0) AS total_net_amount, COUNT(*) AS total_fact_lines
  FROM {{ ref('fct_order_line') }}
  WHERE NOT is_cancelled
) AS f
WHERE m.total_net_sales != f.total_net_amount OR m.total_lines != f.total_fact_lines
