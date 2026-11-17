# Using This GitHub Template

This repository serves as a **GitHub Template** for standing up either:
1. **A Clean Customer / Domain Workspace** (stripping worked example products while keeping the `dpf` CLI, OpenSpec schemas, 13 agent skills, Define/Design templates, and Layer-0 Terraform bootstrap), or
2. **A Live Workshop / PoC Sandbox** (keeping the worked `sales_performance` and `customer_orders` examples ready to run end to end).

> **Agentic Fast Path**: Open this repo in Gemini CLI, Antigravity, Cursor, or Claude Code and run `@Using-This-Template-Prompt.md` to execute the setup interactively.

---

## Option A: Provision a Brand-New GCP Project (Org Admin / Dedicated Sandbox)

Authenticate once (not needed in Cloud Shell):
```bash
gcloud auth login
gcloud auth application-default login
```

### 1. Workshop / Demo Mode (Keep `sales_performance` & `customer_orders`)
```bash
source deploy.sh \
  --project-id my-dpf-demo \
  --region us-central1 \
  --timezone Australia/Perth \
  --relax-domain-policy \
  --presentation-server-url https://my-presentation-server.a.run.app
```
*(Omit `--presentation-server-url` or press Enter when prompted on first run if viewing HTML decks and cockpits locally from disk.)*

### 2. Clean Customer Workspace Mode (Strip Examples First)
```bash
source deploy.sh \
  --clean-examples \
  --project-id foodstuffs-dpf \
  --region australia-southeast1 \
  --timezone Pacific/Auckland
```

---

## Option B: Attach to an Existing Customer Project (Non-Org-Admin)

When Central Cloud Platform provides a pre-created GCP project where you have project-level Owner/Admin rights (without Organization Admin rights):

```bash
./deploy-use-existing-project-non-org-admin.sh \
  --clean-examples \
  --project-id my-existing-gcp-project \
  --region australia-southeast1 \
  --timezone Pacific/Auckland
```

Both scripts ask for an optional **Presentation Server URL** on first run (unless passed via `--presentation-server-url` or `DPF_PRESENTATION_SERVER_URL`) and automatically:
1. Enable all required Google Cloud APIs (BigQuery, BigQuery Data Policy, BigQuery sharing, BigQuery Data Transfer, Data Catalog, Dataform, Knowledge Catalog, Logging, Monitoring).
2. Create Google-managed service identities and custom `dataform-runner` / `dpf-monitor` service accounts with keyless impersonation.
3. Create the GCS state bucket and initial Dataform repository.
4. Hydrate `agent-config.json` (including `presentation_server_url`) and `registry/platform-defaults.yaml` (plus `examples/sales_performance/terraform/terraform.tfvars` in demo mode).

---

## Agent Routing Symlinks

Root symlinks are pre-wired to `AGENTS.md` (which delegates to `openspec/AGENTS.md`):
```text
├── AGENTS.md
├── GEMINI.md -> AGENTS.md
├── CLAUDE.md -> AGENTS.md
├── .cursorrules -> AGENTS.md
└── .clinerules -> AGENTS.md
```

To reset local Layer-0 Terraform caches before targeting a different project, run:
```bash
./clean-up.sh
```
