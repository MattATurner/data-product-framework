output "datasets" {
  description = "Dataset ids by deployment key."
  value       = module.sales_performance.datasets
}

output "policy_tags" {
  description = "Policy tag resource names: pass to dbt with --vars, or read by the Dataform release configuration."
  value       = module.sales_performance.policy_tags
}

output "listings" {
  description = "BigQuery sharing listing resource names."
  value       = module.sales_performance.listings
}
