# dpf: product=sales_performance version=1.2.0 element=model:sales_performance_monthly target=lookml implements=generate-artefacts satisfies=R-1,R-4,R-7,R-8
view: sales_performance_monthly {
  sql_table_name: `@{GCP_PROJECT}.@{DATASET_GOLD}.sales_performance_monthly` ;;

  dimension: _dpf_pk {
    primary_key: yes
    hidden: yes
    type: string
    sql: CONCAT(CAST(${TABLE}.year_month AS STRING), '|', CAST(${TABLE}.customer_segment AS STRING), '|', CAST(${TABLE}.product_category AS STRING), '|', CAST(${TABLE}.region AS STRING)) ;;
  }

  dimension: year_month {
    type: string
    description: "Calendar month of the order date, written YYYY-MM."
    sql: ${TABLE}.year_month ;;
  }

  dimension: customer_segment {
    type: string
    description: "Commercial segment a customer belongs to (for example SMB or Enterprise)."
    sql: ${TABLE}.customer_segment ;;
  }

  dimension: product_category {
    type: string
    description: "Category in the Merchandising product range to which a product belongs."
    sql: ${TABLE}.product_category ;;
  }

  dimension: region {
    type: string
    description: "Sales region of the customer (Australian state or territory code)."
    sql: ${TABLE}.region ;;
  }

  dimension: net_sales {
    type: string
    description: "Gross amount less discount, excluding tax, for order lines that are not cancelled."
    sql: ${TABLE}.net_sales ;;
  }

  dimension: units_sold {
    type: string
    description: "Number of units on order lines that are not cancelled."
    sql: ${TABLE}.units_sold ;;
  }

  dimension: order_line_count {
    type: string
    sql: ${TABLE}.order_line_count ;;
  }

  measure: count {
    type: count
    description: "Row count of sales_performance_monthly"
  }
}
