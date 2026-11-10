# dpf: product=sales_performance environment=test implements=generate-artefacts
# Note: dataset_prefix, prevent_destroy and enforce_policy_tags are baked at generate time
# (`dpf generate sales_performance --env test`); this file supplies runtime Terraform variables.
project_id = "data-products-deploy"
region     = "us-central1"
