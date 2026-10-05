{{ config(tags=['hourly']) }}
-- dpf: test=grain:sales_order_line_detail model=sales_order_line_detail satisfies=R-2,R-8,R-12
SELECT order_id, order_line_no, COUNT(*) AS rows_per_grain
FROM {{ ref('sales_order_line_detail') }}
GROUP BY order_id, order_line_no
HAVING COUNT(*) > 1
