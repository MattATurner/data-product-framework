# dpf: product=sales_performance version=1.2.0 element=model:sales_performance_partner_extract target=lookml implements=generate-artefacts satisfies=R-13
view: sales_performance_partner_extract {
  sql_table_name: `@{GCP_PROJECT}.@{DATASET_SHARE}.sales_performance_partner_extract` ;;

  dimension: _dpf_pk {
    primary_key: yes
    hidden: yes
    type: string
    sql: CONCAT(CAST(${TABLE}.year_month AS STRING), '|', CAST(${TABLE}.product_category AS STRING), '|', CAST(${TABLE}.region AS STRING)) ;;
  }

  dimension: year_month {
    type: string
    description: "Calendar month of the order date, written YYYY-MM."
    sql: ${TABLE}.year_month ;;
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

  measure: count {
    type: count
    description: "Row count of sales_performance_partner_extract"
  }
}
