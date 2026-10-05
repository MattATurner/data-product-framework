{{ config(tags=['hourly', 'monthly']) }}
-- dpf: test=grain_not_null:dim_date model=dim_date satisfies=R-1
SELECT *
FROM {{ ref('dim_date') }}
WHERE date_key IS NULL
