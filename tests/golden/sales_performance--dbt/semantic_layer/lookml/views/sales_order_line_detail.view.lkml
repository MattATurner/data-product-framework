# dpf: product=sales_performance version=1.2.0 element=model:sales_order_line_detail target=lookml implements=generate-artefacts satisfies=R-2,R-8,R-12
view: sales_order_line_detail {
  sql_table_name: `@{GCP_PROJECT}.@{DATASET_GOLD}.sales_order_line_detail` ;;

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

  dimension_group: order {
    type: time
    timeframes: [raw, date, week, month, quarter, year]
    datatype: date
    description: "Date the order was placed."
    sql: ${TABLE}.order_date ;;
  }

  dimension: year_month {
    type: string
    description: "Calendar month of the order date, written YYYY-MM."
    sql: ${TABLE}.year_month ;;
  }

  dimension: customer_id {
    type: string
    sql: ${TABLE}.customer_id ;;
  }

  dimension: customer_name {
    type: string
    description: "A party that places orders, identified by its customer number and name."
    sql: ${TABLE}.customer_name ;;
  }

  dimension: customer_segment {
    type: string
    description: "Commercial segment a customer belongs to (for example SMB or Enterprise)."
    sql: ${TABLE}.customer_segment ;;
  }

  dimension: region {
    type: string
    description: "Sales region of the customer (Australian state or territory code)."
    sql: ${TABLE}.region ;;
  }

  dimension: product_id {
    type: string
    sql: ${TABLE}.product_id ;;
  }

  dimension: product_name {
    type: string
    sql: ${TABLE}.product_name ;;
  }

  dimension: product_category {
    type: string
    description: "Category in the Merchandising product range to which a product belongs."
    sql: ${TABLE}.product_category ;;
  }

  dimension: order_status {
    type: string
    description: "Lifecycle state of an order - placed, fulfilled or cancelled."
    sql: ${TABLE}.order_status ;;
  }

  dimension: is_cancelled {
    type: yesno
    sql: ${TABLE}.is_cancelled ;;
  }

  dimension: quantity {
    type: string
    description: "Number of units on order lines that are not cancelled."
    sql: ${TABLE}.quantity ;;
  }

  dimension: gross_amount {
    type: string
    sql: ${TABLE}.gross_amount ;;
  }

  dimension: discount_amount {
    type: string
    sql: ${TABLE}.discount_amount ;;
  }

  dimension: net_amount {
    type: string
    description: "Gross amount less discount, excluding tax, for order lines that are not cancelled."
    sql: ${TABLE}.net_amount ;;
  }

  dimension: counted_net_amount {
    type: string
    sql: ${TABLE}.counted_net_amount ;;
  }

  measure: count {
    type: count
    description: "Row count of sales_order_line_detail"
  }
}
