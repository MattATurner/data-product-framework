{{ config(tags=['hourly', 'monthly']) }}
-- dpf: test=grain:stg_products model=stg_products satisfies=R-6
SELECT product_id, COUNT(*) AS rows_per_grain
FROM {{ ref('stg_products') }}
GROUP BY product_id
HAVING COUNT(*) > 1
