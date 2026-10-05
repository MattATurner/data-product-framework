{{ config(
    materialized='view',
    schema=var('staging_dataset'),
    tags=['hourly', 'monthly']
) }}
-- dpf: model=stg_customers layer=staging role=staging skill=transform-raw-to-staging satisfies=R-4 implements=conform-staging
SELECT * EXCEPT (_dpf_row_rank, _dpf_version_rank, _reject_reason)
FROM {{ ref('stg_customers__candidates') }}
WHERE _dpf_row_rank = 1 AND _reject_reason IS NULL
