{{ config(tags=['hourly', 'monthly']) }}
-- dpf: test=integrity:fct_order_line:customer_id:not_null model=fct_order_line satisfies=R-2,R-3,R-7,R-8,R-9
SELECT order_id, order_line_no
FROM {{ ref('fct_order_line') }}
WHERE customer_id IS NULL
