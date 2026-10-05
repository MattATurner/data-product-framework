{{ config(tags=['hourly', 'monthly']) }}
-- dpf: test=scd_overlap:dim_product model=dim_product satisfies=R-6
SELECT a.product_id, a.valid_from, a.valid_to, b.valid_from AS overlapping_from
FROM {{ ref('dim_product') }} AS a
JOIN {{ ref('dim_product') }} AS b
  ON a.product_id = b.product_id AND a.version_no < b.version_no
 AND a.valid_from < b.valid_to AND b.valid_from < a.valid_to
