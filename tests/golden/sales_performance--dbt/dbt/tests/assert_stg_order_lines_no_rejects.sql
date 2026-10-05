{{ config(tags=['hourly', 'monthly']) }}
-- dpf: test=reject_gate:stg_order_lines model=stg_order_lines satisfies=R-11
-- depends_on: {{ ref('stg_order_lines') }}
SELECT *
FROM {{ ref('stg_order_lines_rejects') }}
