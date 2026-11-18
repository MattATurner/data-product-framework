-- Typed product rows (one per landed version). dpf adds deduplication and the history view
-- used by dim_product.
SELECT
  CAST(prod_id AS STRING)              AS product_id,
  CAST(prod_name AS STRING)            AS product_name,
  UPPER(CAST(category_cd AS STRING))   AS product_category,
  CAST(last_modified_ts AS TIMESTAMP)  AS source_modified_ts,
  _ingest_ts,
  _batch_id
FROM {{ ref('raw_products') }}
