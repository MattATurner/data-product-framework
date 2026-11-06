# dpf: product=sales_performance version=1.2.0 element=model:fct_order_line target=lookml implements=generate-artefacts satisfies=R-2,R-3,R-7,R-8,R-9
view: fct_order_line {
  sql_table_name: `@{GCP_PROJECT}.@{DATASET_SILVER}.fct_order_line` ;;

  dimension: _dpf_pk {
    primary_key: yes
    hidden: yes
    type: string
    sql: CONCAT(CAST(${TABLE}.order_id AS STRING), '|', CAST(${TABLE}.order_line_no AS STRING)) ;;
  }

  dimension: order_id {
    type: string
    sql: ${TABLE}.order_id ;;
  }

  dimension: order_line_no {
    type: string
    sql: ${TABLE}.order_line_no ;;
  }

  dimension: sk_customer {
    hidden: yes
    type: number
    sql: ${TABLE}.sk_customer ;;
  }

  dimension: customer_id {
    type: string
    sql: ${TABLE}.customer_id ;;
  }

  dimension: sk_product {
    hidden: yes
    type: number
    sql: ${TABLE}.sk_product ;;
  }

  dimension: product_id {
    type: string
    sql: ${TABLE}.product_id ;;
  }

  dimension: date_key {
    hidden: yes
    type: number
    sql: ${TABLE}.date_key ;;
  }

  dimension_group: order {
    type: time
    timeframes: [raw, date, week, month, quarter, year]
    datatype: date
    description: "Date the order was placed."
    sql: ${TABLE}.order_date ;;
  }

  dimension: order_status {
    type: string
    description: "Lifecycle state of an order - placed, fulfilled or cancelled."
    sql: ${TABLE}.order_status ;;
  }

  dimension_group: source_modified {
    type: time
    timeframes: [raw, time, date, week, month, quarter, year]
    datatype: timestamp
    sql: ${TABLE}.source_modified_ts ;;
  }

  dimension: is_cancelled {
    type: yesno
    sql: ${TABLE}.is_cancelled ;;
  }

  measure: count {
    type: count
    description: "Row count of fct_order_line"
  }

  measure: quantity {
    label: "Quantity"
    description: "Quantity"
    type: sum
    sql: ${TABLE}.quantity ;;
  }

  measure: gross_amount {
    label: "Gross Amount"
    description: "Gross Amount"
    type: sum
    sql: ${TABLE}.gross_amount ;;
  }

  measure: discount_amount {
    label: "Discount Amount"
    description: "Discount Amount"
    type: sum
    sql: ${TABLE}.discount_amount ;;
  }

  measure: net_amount {
    label: "Net Amount"
    description: "Net Amount"
    type: sum
    sql: ${TABLE}.net_amount ;;
  }

  measure: net_sales {
    label: "Net Sales (AUD)"
    description: "Net sales in AUD excluding tax and cancelled order lines."
    type: sum
    filters: [is_cancelled: "no"]
    sql: ${TABLE}.net_amount ;;
  }

  measure: units_sold {
    label: "Units Sold"
    description: "Total units sold excluding cancelled order lines."
    type: sum
    filters: [is_cancelled: "no"]
    sql: ${TABLE}.quantity ;;
  }
}
