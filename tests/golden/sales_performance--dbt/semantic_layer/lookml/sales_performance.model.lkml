# dpf: product=sales_performance version=1.2.0 element=semantic_layer target=lookml implements=generate-artefacts satisfies=R-1,R-2,R-4,R-6,R-7,R-8,R-12
connection: "bigquery_sales"

include: "/views/*.view.lkml"
include: "/explores/*.explore.lkml"
include: "/dashboards/*.dashboard.lookml"

datagroup: sales_performance_default_datagroup {
  sql_trigger: SELECT MAX(order_date) FROM `@{GCP_PROJECT}.@{DATASET_SILVER}.fct_order_line` ;;
  max_cache_age: "90 minutes"
}

persist_with: sales_performance_default_datagroup
