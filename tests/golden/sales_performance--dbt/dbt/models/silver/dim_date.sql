{{ config(
    materialized='table',
    schema=var('silver_dataset'),
    tags=['hourly', 'monthly'],
    persist_docs={'relation': true, 'columns': true}
) }}
-- dpf: model=dim_date layer=silver role=calendar skill=kimball/model-date-dimension satisfies=R-1
SELECT
  CAST(FORMAT_DATE('%Y%m%d', d) AS INT64) AS date_key,
  d AS calendar_date,
  EXTRACT(YEAR FROM d) AS year,
  EXTRACT(QUARTER FROM d) AS quarter,
  FORMAT_DATE('%Y-Q%Q', d) AS year_quarter,
  EXTRACT(MONTH FROM d) AS month,
  FORMAT_DATE('%Y-%m', d) AS year_month,
  FORMAT_DATE('%B', d) AS month_name,
  EXTRACT(DAYOFWEEK FROM d) AS day_of_week,
  FORMAT_DATE('%A', d) AS day_name,
  EXTRACT(DAYOFWEEK FROM d) IN (1, 7) AS is_weekend
FROM UNNEST(GENERATE_DATE_ARRAY(DATE '2020-01-01', DATE '2030-12-31')) AS d
