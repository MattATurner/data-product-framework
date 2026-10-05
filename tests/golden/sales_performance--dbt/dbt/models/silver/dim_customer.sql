{{ config(
    materialized='table',
    schema=var('silver_dataset'),
    tags=['hourly', 'monthly'],
    persist_docs={'relation': true, 'columns': true}
) }}
-- dpf: model=dim_customer layer=silver role=dimension skill=kimball/model-scd satisfies=R-4,R-5,R-12
WITH history AS (
  SELECT customer_id, customer_segment, region, source_modified_ts
  FROM {{ ref('stg_customers_history') }}
),
changes AS (
  SELECT
    *,
    TO_JSON_STRING(STRUCT(customer_segment, region)) AS _dpf_tracked,
    LAG(TO_JSON_STRING(STRUCT(customer_segment, region))) OVER (PARTITION BY customer_id ORDER BY source_modified_ts) AS _dpf_previous
  FROM history
),
versions AS (
  SELECT
    customer_id, customer_segment, region,
    source_modified_ts AS changed_at,
    ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY source_modified_ts) AS version_no,
    LEAD(source_modified_ts) OVER (PARTITION BY customer_id ORDER BY source_modified_ts) AS next_changed_at
  FROM changes
  WHERE _dpf_previous IS NULL OR _dpf_previous != _dpf_tracked
),
current_values AS (
  SELECT customer_id, customer_name, customer_email, customer_phone
  FROM {{ ref('stg_customers') }}
)
SELECT
  FARM_FINGERPRINT(CONCAT(CAST(v.customer_id AS STRING), '|', CAST(v.version_no AS STRING))) AS sk_customer,
  v.customer_id,
  v.customer_segment,
  v.region,
  c.customer_name,
  c.customer_email,
  c.customer_phone,
  IF(v.version_no = 1, TIMESTAMP '1900-01-01 00:00:00+00', v.changed_at) AS valid_from,
  COALESCE(v.next_changed_at, TIMESTAMP '9999-12-31 00:00:00+00') AS valid_to,
  v.next_changed_at IS NULL AS is_current,
  v.version_no
FROM versions AS v
LEFT JOIN current_values AS c ON c.customer_id = v.customer_id
UNION ALL
-- unknown member: facts whose reference has not arrived resolve here instead of being dropped
SELECT -1, 'UNKNOWN', 'UNKNOWN', 'UNKNOWN', NULL, NULL, NULL, TIMESTAMP '1900-01-01 00:00:00+00', TIMESTAMP '9999-12-31 00:00:00+00', TRUE, 0
