{{ config(tags=['monthly']) }}
-- dpf: test=grain:sales_performance_partner_extract model=sales_performance_partner_extract satisfies=R-13
SELECT year_month, product_category, region, COUNT(*) AS rows_per_grain
FROM {{ ref('sales_performance_partner_extract') }}
GROUP BY year_month, product_category, region
HAVING COUNT(*) > 1
