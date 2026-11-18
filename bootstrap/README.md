# Layer 0 — Workspace Bootstrap & GitHub Template Onboarding (`bootstrap/`)

This directory sets up a clean customer workspace or live PoC sandbox from the Data Product Framework GitHub Template so every `dpf` product module applies cleanly on first run without manual console clicks.

> **Agentic Fast Path**: Open this repository in Gemini CLI, Antigravity, Cursor, or Claude Code and run `@bootstrap/onboarding-prompt.md` to execute onboarding interactively.

---

## Two-Layer Separation

1. **Layer 0 (`bootstrap/terraform/` — run once per environment)**:
   - Optionally creates a new GCP project (`project_number == ""`) or attaches to an existing customer project (`project_number != ""`, `org_id = "0"`).
   - Enables all required Google Cloud APIs (BigQuery, BigQuery Data Policy, BigQuery sharing, BigQuery Data Transfer, Data Catalog, Dataform, Knowledge Catalog, Logging, Monitoring, Storage, IAM).
   - Provisions a keyless impersonated deployment service account (`dpf-deployer@...`), Google-managed service identities, and custom `dataform-runner` / `dpf-monitor` service accounts.
   - Creates the state/output bucket (`gs://<project_id>-dpf-state`) and initial Dataform repository.
   - Prompts once on first run for an optional **Presentation Server URL** (unless passed via `--presentation-server-url` or `DPF_PRESENTATION_SERVER_URL`) and hydrates `registry/agent-config.json` and `registry/platform-defaults.yaml`.
2. **Layer 1..N (`generated/<product>/terraform/` — owned by `dpf generate <product>`)**:
   - Remains 100% generated per data product from `products/<id>/product.yaml` (or `examples/<id>/product.yaml` in demo mode).

---

## Entrypoints

Authenticate once (not needed in Cloud Shell):
```bash
gcloud auth login
gcloud auth application-default login
```

### Option A: Provision a Brand-New GCP Project (Org Admin / Dedicated Sandbox)

* **1. Workshop / Demo Mode** (keep `examples/sales_performance` and `examples/customer_orders`):
  ```bash
  source bootstrap/deploy.sh \
    --project-id my-dpf-demo \
    --region us-central1 \
    --timezone Australia/Perth \
    --relax-domain-policy
  ```
* **2. Clean Customer Workspace Mode** (strip worked examples first):
  ```bash
  source bootstrap/deploy.sh \
    --clean-examples \
    --project-id acme-dpf \
    --region australia-southeast1 \
    --timezone Pacific/Auckland
  ```

### Option B: Attach to an Existing Customer Project (Non-Org-Admin)

```bash
./bootstrap/deploy-existing-project.sh \
  --clean-examples \
  --project-id my-existing-gcp-project \
  --region australia-southeast1 \
  --timezone Pacific/Auckland
```

### Option C: Offline-Only Setup or Reset

```bash
# Hydrate local timezone, region, and optional Presentation Server URL without Terraform:
python3 bootstrap/hydrate_workspace.py --offline --region us-central1 --timezone Australia/Perth

# Reset local Layer-0 Terraform caches (add --strip-examples to remove worked examples):
./bootstrap/clean-up.sh
```
