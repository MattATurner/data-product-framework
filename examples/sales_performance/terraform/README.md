# Infrastructure

```bash
terraform init
terraform plan -var project_id=data-product-framework
terraform apply
```

Creates the six datasets in `us-central1` and the policy tag satisfying BRD R-12.

**Not covered here:**

- **BigQuery sharing listing** for the partner extract (R-13). Create it after the gold
  table exists, so the listing points at a real dataset.
- **Dataform repository and release configuration.** No MCP surface and no clean
  Terraform path at time of writing — see `registry/mcp_servers.yaml`
  (`no_mcp_option_yet`). Create via console or `gcloud`.
