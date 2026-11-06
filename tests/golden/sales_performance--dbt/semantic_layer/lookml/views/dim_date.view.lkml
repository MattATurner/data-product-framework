# dpf: product=sales_performance version=1.2.0 element=model:dim_date target=lookml implements=generate-artefacts satisfies=R-1
view: dim_date {
  sql_table_name: `@{GCP_PROJECT}.@{DATASET_SILVER}.dim_date` ;;

  dimension: date_key {
    primary_key: yes
    type: number
    sql: ${TABLE}.date_key ;;
  }

  dimension_group: calendar {
    type: time
    timeframes: [raw, date, week, month, quarter, year]
    datatype: date
    sql: ${TABLE}.calendar_date ;;
  }

  dimension: year {
    type: number
    sql: ${TABLE}.year ;;
  }

  dimension: quarter {
    type: number
    sql: ${TABLE}.quarter ;;
  }

  dimension: year_quarter {
    type: string
    sql: ${TABLE}.year_quarter ;;
  }

  dimension: month {
    type: number
    description: "Calendar month of the order date, written YYYY-MM."
    sql: ${TABLE}.month ;;
  }

  dimension: year_month {
    type: string
    description: "Calendar month of the order date, written YYYY-MM."
    sql: ${TABLE}.year_month ;;
  }

  dimension: month_name {
    type: string
    sql: ${TABLE}.month_name ;;
  }

  dimension: day_of_week {
    type: number
    sql: ${TABLE}.day_of_week ;;
  }

  dimension: day_name {
    type: string
    sql: ${TABLE}.day_name ;;
  }

  dimension: is_weekend {
    type: yesno
    sql: ${TABLE}.is_weekend ;;
  }

  measure: count {
    type: count
    description: "Row count of dim_date"
  }
}
