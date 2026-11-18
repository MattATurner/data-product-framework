# Layer 0 — Workspace Bootstrap & GitHub Template Onboarding (`bootstrap/`)

This directory sets up a clean customer workspace or live PoC sandbox from the Data Product Framework GitHub Template so every `dpf` product module applies cleanly on first run without manual console clicks.

> **Agentic Fast Path**: Open this repository in Gemini CLI, Antigravity, Cursor, or Claude Code and run `@bootstrap/onboarding-prompt.md` to execute onboarding interactively.

---

## Two-Layer Separation

1. **Layer 0 (`bootstrap/terraform/` — run once per environment)**:
   - Auto-discovers the active `gcloud` user account, 12-digit Organization ID (or `--folder-id`), and open Billing Account when creating a new GCP project (`project_number == ""`, appending a 4-char collision-free suffix unless `--no-random-suffix` is set), or attaches to an existing customer project (`project_number != ""`, `org_id = "0"`).
   - Enables all required Google Cloud APIs (BigQuery, BigQuery Data Policy, BigQuery sharing, BigQuery Data Transfer, Data Catalog, Dataform, Knowledge Catalog, Logging, Monitoring, Storage, IAM).
   - Provisions a keyless impersonated deployment service account (`dpf-deployer@...` — zero exported JSON keys), Google-managed service identities, and custom `dataform-runner` / `dpf-monitor` service accounts, optionally relaxing `iam.allowedPolicyMemberDomains` (`--relax-domain-policy`) for sandbox cross-domain sharing tests.
   - Creates the state/output bucket (`gs://<project_id>-dpf-state`) and initial Dataform repository, and backs up `tf-output.json` and `terraform.tfstate` to `gs://<project_id>-dpf-state/terraform/`.
   - Prompts once on first run for an optional **Presentation Server URL** (unless passed via `--presentation-server-url` or `DPF_PRESENTATION_SERVER_URL`), hydrates `registry/agent-config.json` and `registry/platform-defaults.yaml`, pre-populates `examples/sales_performance/terraform/terraform.tfvars` (if worked examples are retained), and re-stamps worked-example golden copies (`dpf generate --all --update-golden`) when `dpf` is installed.
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

---

## CLI Flag Reference

| Flag | Applies to | Description |
|---|---|---|
| `--project-id <id>` | `deploy.sh`, `deploy-existing-project.sh`, `hydrate_workspace.py` | Base GCP Project ID when creating a new project (default `dpf-workspace`), or existing Project ID |
| `--no-random-suffix` | `deploy.sh` | Use the exact `--project-id` instead of appending a 4-character collision-free suffix |
| `--org-id <id>` / `--folder-id <id>` | `deploy.sh` | 12-digit Organization ID (auto-discovered if unique) or parent Folder ID |
| `--billing-account <id>` | `deploy.sh` | Billing Account ID (`XXXXXX-XXXXXX-XXXXXX`; auto-discovered if unique) |
| `--project-number <num>` | `deploy-existing-project.sh` | 12-digit Project Number (auto-discovered via `gcloud projects describe` if omitted) |
| `--account <email>` | `deploy-existing-project.sh` | Active `gcloud` principal email (auto-discovered if omitted) |
| `--region <region>` | all | Primary GCP region for BigQuery, Dataform, and Knowledge Catalog (default `us-central1`) |
| `--timezone <iana_tz>` | all | Business calendar timezone written to `registry/platform-defaults.yaml` (default `Australia/Perth`) |
| `--dataform-repo <name>` | `deploy.sh`, `deploy-existing-project.sh` | Initial Dataform repository name (default `sales-performance`) |
| `--relax-domain-policy` | `deploy.sh` | Relax `iam.allowedPolicyMemberDomains` on the sandbox project for cross-domain BigQuery sharing tests |
| `--presentation-server-url <url>` | all | Optional Presentation Server URL saved to `registry/agent-config.json` (or `DPF_PRESENTATION_SERVER_URL`) |
| `--fhd-server-url <url>` | all | Optional FHD Server URL saved to `registry/agent-config.json` (or `DPF_FHD_SERVER_URL`) |
| `--clean-examples` | `deploy.sh`, `deploy-existing-project.sh` | Run `bootstrap/clean-up.sh --strip-examples` before provisioning to remove worked examples & demo decks |
| `--yes`, `-y` | `deploy.sh`, `deploy-existing-project.sh` | Skip interactive confirmation and optional Presentation Server prompt for automated runs |
