{{ config(tags=['hourly', 'monthly']) }}
-- dpf: test=grain:dim_product model=dim_product satisfies=R-6
SELECT product_id, valid_from, COUNT(*) AS rows_per_grain
FROM {{ ref('dim_product') }}
GROUP BY product_id, valid_from
HAVING COUNT(*) > 1
