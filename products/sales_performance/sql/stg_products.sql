-- Typed product rows (one per landed version). dpf adds deduplication and the history view
-- used by dim_product.
SELECT
  CAST(PROD_ID AS STRING)              AS product_id,
  CAST(PROD_NAME AS STRING)            AS product_name,
  UPPER(CAST(CATEGORY_CD AS STRING))   AS product_category,
  CAST(LAST_MODIFIED_TS AS TIMESTAMP)  AS source_modified_ts,
  _ingest_ts,
  _batch_id
FROM {{ ref('raw_products') }}
