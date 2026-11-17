I have just created a new repository from the Data Product Framework (DPF) GitHub Template. Execute the workspace onboarding setup with me step by step.

First, ask me five concise questions and wait for my answers:
1. **Workspace Mode**: `customer` (strip worked example products for a clean production/customer repo) or `demo` (keep `sales_performance` and `customer_orders` for a live showcase/training)?
2. **Project / Engagement Name**: e.g. `foodstuffs-dpf` (format as `kebab-case` for GCP project prefix).
3. **Cloud Region & Business Timezone**: e.g. `australia-southeast1` and `Pacific/Auckland` (or keep defaults `us-central1` and `Australia/Perth`).
4. **GCP Deployment Target**:
   - `new-project` (I have Org/Folder Admin + billing access — run `deploy.sh`),
   - `existing-project` (I have an existing GCP Project ID without Org Admin — run `deploy-use-existing-project-non-org-admin.sh`), or
   - `offline-only` (configure local YAML/Python environment now and skip Terraform apply).
5. **Presentation Server URL (Optional)**: Base URL of your HTML Presentation Server if hosting decks, whitepapers, and semantic cockpits centrally (e.g. `https://my-presentation-server.a.run.app`), or `local` / leave blank to open HTML files directly from disk.

Once I reply, execute these steps in exact order:

### Step 1: Python Environment & Symlink Check
- Verify `.cursorrules`, `.clinerules`, `CLAUDE.md`, and `GEMINI.md` symlink to `AGENTS.md` (recreate with `ln -sf AGENTS.md ...` if missing).
- Ensure `.venv` exists and `dpf` is installed (`python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`).

### Step 2: Clean Customer Mode (Only if `customer` was selected)
- Run `bash ./clean-up.sh --strip-examples` to remove worked example products, demo decks, and golden fixtures while preserving `framework/`, `openspec/`, `registry/`, `bootstrap/`, `.agents/`, and `dpf/`.

### Step 3: Configure Defaults or Run Layer-0 Terraform Bootstrap
- Pass `--presentation-server-url <url>` when a Presentation Server URL was provided (or `""` if `local` / skipped).
- If `offline-only`: run `python3 bootstrap/hydrate_workspace.py --offline --project-id <kebab-name> --region <region> --timezone <timezone> --presentation-server-url "<url>"`.
- If `new-project`: run `./deploy.sh --project-id <kebab-name> --region <region> --timezone <timezone> --presentation-server-url "<url>"` (adding `--relax-domain-policy` if testing cross-domain BigQuery sharing listings in a sandbox).
- If `existing-project`: ask for the existing `project_id` if not already given, then run `./deploy-use-existing-project-non-org-admin.sh --project-id <project_id> --region <region> --timezone <timezone> --presentation-server-url "<url>"`.

### Step 4: Verification Gate
- Run `.venv/bin/dpf check --all --gate G3` and `terraform -chdir=bootstrap/terraform validate` (after `init -backend=false` if offline) and report the final workspace status and recommended first command (`framework/templates/define/` or `author-brd`).
