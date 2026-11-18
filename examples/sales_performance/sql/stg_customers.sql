-- Typed customer rows (one per landed version). dpf wraps this body with deduplication on
-- the natural key, the quarantine rules and the history view used by dim_customer.
-- Engine-neutral: {{ ref('...') }} and {{ var('...') }} are rendered per engine.
SELECT
  CAST(cust_id AS STRING)             AS customer_id,
  CAST(cust_name AS STRING)           AS customer_name,
  UPPER(CAST(segment_cd AS STRING))   AS customer_segment,
  UPPER(CAST(region_cd AS STRING))    AS region,
  CAST(email AS STRING)               AS customer_email,
  CAST(phone AS STRING)               AS customer_phone,
  CAST(last_modified_ts AS TIMESTAMP) AS source_modified_ts,
  _ingest_ts,
  _batch_id
FROM {{ ref('raw_customers') }}
