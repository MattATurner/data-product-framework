# dpf: product=sales_performance version=1.2.0 element=model:dim_product target=lookml implements=generate-artefacts satisfies=R-6
view: dim_product {
  sql_table_name: `@{GCP_PROJECT}.@{DATASET_SILVER}.dim_product` ;;

  dimension: sk_product {
    primary_key: yes
    hidden: yes
    type: number
    sql: ${TABLE}.sk_product ;;
  }

  dimension: product_id {
    type: string
    sql: ${TABLE}.product_id ;;
  }

  dimension: valid_from {
    type: string
    sql: ${TABLE}.valid_from ;;
  }

  dimension: product_category {
    type: string
    description: "Category in the Merchandising product range to which a product belongs."
    sql: ${TABLE}.product_category ;;
  }

  dimension: product_name {
    type: string
    sql: ${TABLE}.product_name ;;
  }

  dimension_group: valid_to {
    type: time
    timeframes: [raw, date, week, month, quarter, year]
    datatype: date
    sql: ${TABLE}.valid_to ;;
  }

  dimension: is_current {
    type: yesno
    sql: ${TABLE}.is_current ;;
  }

  dimension: version_no {
    type: number
    sql: ${TABLE}.version_no ;;
  }

  measure: count {
    type: count
    description: "Row count of dim_product"
  }
}
