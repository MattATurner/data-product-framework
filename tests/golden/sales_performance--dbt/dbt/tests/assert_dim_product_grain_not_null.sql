{{ config(tags=['hourly', 'monthly']) }}
-- dpf: test=grain_not_null:dim_product model=dim_product satisfies=R-6
SELECT *
FROM {{ ref('dim_product') }}
WHERE product_id IS NULL OR valid_from IS NULL
