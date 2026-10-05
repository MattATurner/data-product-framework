{{ config(tags=['hourly', 'monthly']) }}
-- dpf: test=scd_overlap:dim_customer model=dim_customer satisfies=R-4,R-5,R-12
SELECT a.customer_id, a.valid_from, a.valid_to, b.valid_from AS overlapping_from
FROM {{ ref('dim_customer') }} AS a
JOIN {{ ref('dim_customer') }} AS b
  ON a.customer_id = b.customer_id AND a.version_no < b.version_no
 AND a.valid_from < b.valid_to AND b.valid_from < a.valid_to
