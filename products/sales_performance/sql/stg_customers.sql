-- Typed customer rows (one per landed version). dpf wraps this body with deduplication on
-- the natural key, the quarantine rules and the history view used by dim_customer.
-- Engine-neutral: {{ ref('...') }} and {{ var('...') }} are rendered per engine.
SELECT
  CAST(CUST_ID AS STRING)             AS customer_id,
  CAST(CUST_NAME AS STRING)           AS customer_name,
  UPPER(CAST(SEGMENT_CD AS STRING))   AS customer_segment,
  UPPER(CAST(REGION_CD AS STRING))    AS region,
  CAST(EMAIL AS STRING)               AS customer_email,
  CAST(PHONE AS STRING)               AS customer_phone,
  CAST(LAST_MODIFIED_TS AS TIMESTAMP) AS source_modified_ts,
  _ingest_ts,
  _batch_id
FROM {{ ref('raw_customers') }}
