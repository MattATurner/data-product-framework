{{ config(
    materialized='view',
    schema=var('staging_dataset'),
    tags=['hourly', 'monthly']
) }}
-- dpf: model=stg_order_lines layer=staging role=staging skill=transform-raw-to-staging satisfies=R-11 implements=conform-staging part=rejects
SELECT * EXCEPT (_dpf_row_rank, _dpf_version_rank)
FROM {{ ref('stg_order_lines__candidates') }}
WHERE (_dpf_row_rank = 1 OR order_id IS NULL OR order_line_no IS NULL) AND _reject_reason IS NOT NULL
