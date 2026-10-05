{{ config(tags=['hourly']) }}
-- dpf: test=grain:sales_performance_monthly model=sales_performance_monthly satisfies=R-1,R-4,R-7,R-8
SELECT year_month, customer_segment, product_category, region, COUNT(*) AS rows_per_grain
FROM {{ ref('sales_performance_monthly') }}
GROUP BY year_month, customer_segment, product_category, region
HAVING COUNT(*) > 1
