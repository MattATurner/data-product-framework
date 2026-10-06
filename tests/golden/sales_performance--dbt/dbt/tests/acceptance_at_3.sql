{{ config(tags=['acceptance']) }}
-- dpf: test=acceptance:AT-3 model=fct_order_line satisfies=R-3 verifies=AX-3
SELECT COUNT(*) AS line_rows, MAX(quantity) AS max_quantity, MAX(net_amount) AS max_net_amount
FROM {{ ref('fct_order_line') }}
WHERE order_id = 'SO-1001' AND order_line_no = 2
HAVING COUNT(*) != 1 OR MAX(quantity) != 6 OR MAX(net_amount) != 810
