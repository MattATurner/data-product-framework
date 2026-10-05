{{ config(tags=['hourly']) }}
-- dpf: test=grain_not_null:sales_order_line_detail model=sales_order_line_detail satisfies=R-2,R-8,R-12
SELECT *
FROM {{ ref('sales_order_line_detail') }}
WHERE order_id IS NULL OR order_line_no IS NULL
