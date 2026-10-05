{{ config(severity='warn', tags=['hourly', 'monthly']) }}
-- dpf: test=integrity:fct_order_line:dim_product:late_arrival model=fct_order_line satisfies=R-2,R-3,R-7,R-8,R-9 severity=warn
SELECT order_id, order_line_no, product_id
FROM {{ ref('fct_order_line') }}
WHERE sk_product = -1
