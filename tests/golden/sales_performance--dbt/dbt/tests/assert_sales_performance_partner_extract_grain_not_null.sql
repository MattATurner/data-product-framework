{{ config(tags=['monthly']) }}
-- dpf: test=grain_not_null:sales_performance_partner_extract model=sales_performance_partner_extract satisfies=R-13
SELECT *
FROM {{ ref('sales_performance_partner_extract') }}
WHERE year_month IS NULL OR product_category IS NULL OR region IS NULL
