{{ config(tags=['hourly', 'monthly']) }}
-- dpf: test=grain:stg_customers model=stg_customers satisfies=R-4
SELECT customer_id, COUNT(*) AS rows_per_grain
FROM {{ ref('stg_customers') }}
GROUP BY customer_id
HAVING COUNT(*) > 1
