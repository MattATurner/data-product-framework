{{ config(tags=['hourly', 'monthly']) }}
-- dpf: test=grain:stg_order_lines model=stg_order_lines satisfies=R-3,R-11
SELECT order_id, order_line_no, COUNT(*) AS rows_per_grain
FROM {{ ref('stg_order_lines') }}
GROUP BY order_id, order_line_no
HAVING COUNT(*) > 1
