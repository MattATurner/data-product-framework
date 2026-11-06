# dpf: product=sales_performance version=1.2.0 element=explore:order_lines target=lookml implements=generate-artefacts satisfies=R-1,R-2,R-4,R-6,R-7,R-8,R-12
include: "/views/*.view.lkml"

explore: order_lines {
  view_name: fct_order_line
  label: "Sales Performance — Order Lines"
  description: "Order-line sales joined to point-in-time customer segment, product category and calendar."

  conditionally_filter: {
    filters: [fct_order_line.order_date: "90 days"]
    unless: [dim_date.year_month, dim_date.year_quarter, dim_date.year, dim_date.calendar_date]
  }

  join: dim_customer {
    type: left_outer
    relationship: many_to_one
    sql_on: ${fct_order_line.sk_customer} = ${dim_customer.sk_customer} ;;
  }

  join: dim_product {
    type: left_outer
    relationship: many_to_one
    sql_on: ${fct_order_line.sk_product} = ${dim_product.sk_product} ;;
  }

  join: dim_date {
    type: left_outer
    relationship: many_to_one
    sql_on: ${fct_order_line.date_key} = ${dim_date.date_key} ;;
  }

  aggregate_table: sales_performance_monthly {
    query: {
      dimensions: [dim_date.year_month, dim_customer.customer_segment, dim_product.product_category, dim_customer.region]
      measures: [fct_order_line.count, fct_order_line.net_sales, fct_order_line.units_sold]
    }
    materialization: {
      datagroup_trigger: sales_performance_default_datagroup
    }
  }
}
