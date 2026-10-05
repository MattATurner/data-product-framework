{{ config(tags=['hourly', 'monthly']) }}
-- dpf: test=grain:dim_date model=dim_date satisfies=R-1
SELECT date_key, COUNT(*) AS rows_per_grain
FROM {{ ref('dim_date') }}
GROUP BY date_key
HAVING COUNT(*) > 1
