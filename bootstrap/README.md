# Layer 0 — Workspace Foundation Bootstrap (`bootstrap/terraform`)

This module sets up a Google Cloud project so any Data Product Framework (`dpf`) product module can apply cleanly on the first run without manual console steps.

## Two-Layer Separation

1. **Layer 0 (`bootstrap/terraform/` — run once per environment via `source deploy.sh`)**:
   - Optionally creates a new GCP project (`project_number == ""`) or attaches to an existing customer project (`project_number != ""`, `org_id = "0"`).
   - Enables all required Google Cloud APIs (BigQuery, BigQuery Data Policy, BigQuery sharing, BigQuery Data Transfer, Data Catalog, Dataform, Knowledge Catalog, Logging, Monitoring, Storage, IAM).
   - Provisions a keyless impersonated deployment service account (`dpf-deployer@...`).
   - Creates the three Google-managed service identities (`dataplex`, `dataform`, `bigquerydatatransfer`).
   - Creates `dataform-runner` and `dpf-monitor` service accounts with strict `actAs` and `TokenCreator` bindings.
   - Creates the state/output bucket (`gs://<project_id>-dpf-state`) and initial Dataform repository.
   - Automatically hydrates `registry/platform-defaults.yaml` and `agent-config.json`.
2. **Layer 1..N (`generated/<product>/terraform/` — owned by `dpf generate <product>`)**:
   - Remains 100% generated per data product from `products/<id>/product.yaml`.

## Entrypoints

- **New GCP Project (Org Admin / Dedicated Sandbox)**:
  ```bash
  source deploy.sh
  ```
- **Existing Customer Project (Non-Org-Admin)**:
  ```bash
  source deploy-use-existing-project-non-org-admin.sh --project-id <my-project>
  ```
