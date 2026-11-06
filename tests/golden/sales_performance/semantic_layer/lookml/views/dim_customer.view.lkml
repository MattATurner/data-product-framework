# dpf: product=sales_performance version=1.2.0 element=model:dim_customer target=lookml implements=generate-artefacts satisfies=R-4,R-5,R-12
view: dim_customer {
  sql_table_name: `@{GCP_PROJECT}.@{DATASET_SILVER}.dim_customer` ;;

  dimension: sk_customer {
    primary_key: yes
    hidden: yes
    type: number
    sql: ${TABLE}.sk_customer ;;
  }

  dimension: customer_id {
    type: string
    sql: ${TABLE}.customer_id ;;
  }

  dimension: valid_from {
    type: string
    sql: ${TABLE}.valid_from ;;
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

  dimension: customer_name {
    type: string
    description: "A party that places orders, identified by its customer number and name."
    sql: ${TABLE}.customer_name ;;
  }

  dimension: customer_email {
    type: string
    sql: ${TABLE}.customer_email ;;
  }

  dimension: customer_phone {
    type: string
    sql: ${TABLE}.customer_phone ;;
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
    description: "Row count of dim_customer"
  }
}
