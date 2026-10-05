{{ config(tags=['hourly', 'monthly']) }}
-- dpf: test=grain_not_null:stg_order_lines model=stg_order_lines satisfies=R-3,R-11
SELECT *
FROM {{ ref('stg_order_lines') }}
WHERE order_id IS NULL OR order_line_no IS NULL
