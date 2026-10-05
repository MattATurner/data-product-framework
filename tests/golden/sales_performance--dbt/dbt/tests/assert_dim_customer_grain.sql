{{ config(tags=['hourly', 'monthly']) }}
-- dpf: test=grain:dim_customer model=dim_customer satisfies=R-4,R-5,R-12
SELECT customer_id, valid_from, COUNT(*) AS rows_per_grain
FROM {{ ref('dim_customer') }}
GROUP BY customer_id, valid_from
HAVING COUNT(*) > 1
