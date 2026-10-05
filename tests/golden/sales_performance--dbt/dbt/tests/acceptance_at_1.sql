{{ config(tags=['acceptance']) }}
-- dpf: test=acceptance:AT-1 model=sales_performance_monthly satisfies=R-1 verifies=AX-1
WITH quarters AS (
  SELECT DISTINCT year_month, year_quarter FROM {{ ref('dim_date') }}
),
from_monthly AS (
  SELECT q.year_quarter AS quarter, m.customer_segment AS segment, SUM(m.net_sales) AS monthly_net_sales
  FROM {{ ref('sales_performance_monthly') }} AS m
  JOIN quarters AS q ON q.year_month = m.year_month
  GROUP BY q.year_quarter, m.customer_segment
),
from_detail AS (
  SELECT q.year_quarter AS quarter, l.customer_segment AS segment, SUM(l.net_amount) AS detail_net_sales
  FROM {{ ref('sales_order_line_detail') }} AS l
  JOIN quarters AS q ON q.year_month = l.year_month
  WHERE NOT l.is_cancelled
  GROUP BY q.year_quarter, l.customer_segment
)
SELECT quarter, segment, m.monthly_net_sales, d.detail_net_sales
FROM from_monthly AS m
FULL OUTER JOIN from_detail AS d USING (quarter, segment)
WHERE m.monthly_net_sales IS NULL OR d.detail_net_sales IS NULL
   OR m.monthly_net_sales != d.detail_net_sales
