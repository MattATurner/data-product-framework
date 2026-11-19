#!/usr/bin/env bash
####################################################################################
# Copyright 2026 Google LLC — Apache License 2.0
#
# Data Product Framework (DPF) — Layer-0 Workspace Bootstrap (Creates New GCP Project)
#
# Mirrors the l400-agentic-data-analytics deployment workflow:
#   1. Auto-discovers active gcloud user, Organization ID, and Billing Account
#   2. Runs Layer-0 Terraform in bootstrap/terraform/ (creates project, enables APIs,
#      creates service identities, dataform-runner & dpf-monitor SAs, Dataform repo,
#      and state bucket via keyless Service Account Impersonation)
#   3. Backs up tf-output.json & terraform.tfstate to GCS
#   4. Hydrates agent-config.json and registry/platform-defaults.yaml automatically
#
# USAGE:
#   ./bootstrap/deploy.sh
#   ./bootstrap/deploy.sh --project-id my-dpf-demo --region australia-southeast1 --timezone Pacific/Auckland
#   ./bootstrap/deploy.sh --clean-examples --project-id acme-dpf --region australia-southeast1 --timezone Pacific/Auckland
####################################################################################

if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
  echo "Error: run ./bootstrap/deploy.sh directly instead of sourcing it." >&2
  return 1
fi

set -euo pipefail

PROJECT_ID="dpf-workspace"
REGION="us-central1"
TIMEZONE="Australia/Perth"
DATAFORM_REPO="sales-performance"
DATAFORM_REPO_SET="false"
ORG_ID=""
FOLDER_ID=""
BILLING_ACCOUNT=""
APPEND_RANDOM="true"
RELAX_DOMAIN_POLICY="false"
CLEAN_EXAMPLES="false"
AUTO_CONFIRM="false"
PRESENTATION_SERVER_URL="${DPF_PRESENTATION_SERVER_URL:-}"
PRESENTATION_URL_SET="false"
FHD_SERVER_URL="${DPF_FHD_SERVER_URL:-}"
FHD_URL_SET="false"
if [[ -n "${PRESENTATION_SERVER_URL}" ]]; then PRESENTATION_URL_SET="true"; fi
if [[ -n "${FHD_SERVER_URL}" ]]; then FHD_URL_SET="true"; fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-id)              PROJECT_ID="${2:?Missing value for --project-id}"; shift 2 ;;
    --region)                  REGION="${2:?Missing value for --region}"; shift 2 ;;
    --timezone)                TIMEZONE="${2:?Missing value for --timezone}"; shift 2 ;;
    --dataform-repo)           DATAFORM_REPO="${2:?Missing value for --dataform-repo}"; DATAFORM_REPO_SET="true"; shift 2 ;;
    --org-id)                  ORG_ID="${2:?Missing value for --org-id}"; shift 2 ;;
    --folder-id)               FOLDER_ID="${2:?Missing value for --folder-id}"; shift 2 ;;
    --billing-account)         BILLING_ACCOUNT="${2:?Missing value for --billing-account}"; shift 2 ;;
    --no-random-suffix)        APPEND_RANDOM="false"; shift ;;
    --relax-domain-policy)     RELAX_DOMAIN_POLICY="true"; shift ;;
    --presentation-server-url) PRESENTATION_SERVER_URL="${2:?Missing value for --presentation-server-url}"; PRESENTATION_URL_SET="true"; shift 2 ;;
    --fhd-server-url)          FHD_SERVER_URL="${2:?Missing value for --fhd-server-url}"; FHD_URL_SET="true"; shift 2 ;;
    --clean-examples)          CLEAN_EXAMPLES="true"; shift ;;
    --yes|-y)                  AUTO_CONFIRM="true"; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd -P)"

if [[ "${CLEAN_EXAMPLES}" == "true" ]]; then
  if [[ "${DATAFORM_REPO_SET}" != "true" ]]; then
    DATAFORM_REPO="${PROJECT_ID}"
  fi
  echo "==> Stripping worked example material to create a clean customer workspace..."
  bash "${SCRIPT_DIR}/clean-up.sh" --strip-examples
fi

if [[ "${AUTO_CONFIRM}" != "true" && "${PRESENTATION_URL_SET}" != "true" ]]; then
  existing_pres_url=$(python3 -c 'import json,sys,pathlib; p=pathlib.Path(sys.argv[1]); print((json.loads(p.read_text()).get("presentation_server_url") or "") if p.is_file() else "")' "${REPO_ROOT}/registry/agent-config.json" 2>/dev/null || true)
  if [[ -n "${existing_pres_url}" ]]; then
    PRESENTATION_SERVER_URL="${existing_pres_url}"
  else
    read -r -p "Optional Presentation Server URL for hosting HTML decks/cockpits (e.g. https://...a.run.app, or press Enter for local-only): " PRESENTATION_SERVER_URL
    PRESENTATION_URL_SET="true"
  fi
fi

gcp_account_name=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -n 1 || true)
if [[ -z "${gcp_account_name}" ]]; then
  echo "No active gcloud account found. Run: gcloud auth login && gcloud auth application-default login" >&2
  exit 1
fi

if [[ -z "${ORG_ID}" && -z "${FOLDER_ID}" ]]; then
  mapfile -t org_list < <(gcloud organizations list --format="value(ID)" 2>/dev/null || true)
  if [[ ${#org_list[@]} -eq 1 && -n "${org_list[0]}" ]]; then
    ORG_ID="${org_list[0]}"
    echo "Organization ID automatically retrieved: ${ORG_ID}"
  elif [[ "${AUTO_CONFIRM}" == "true" ]]; then
    echo "Error: could not uniquely determine Organization ID under --yes; pass --org-id or --folder-id." >&2
    exit 1
  else
    echo "Could not uniquely determine Organization ID (found ${#org_list[@]})."
    read -r -p "Please enter your 12-digit Organization ID (or leave blank if using --folder-id): " ORG_ID
  fi
fi

if [[ -z "${BILLING_ACCOUNT}" ]]; then
  mapfile -t bill_list < <(gcloud billing accounts list --filter="open=true" --format="value(ACCOUNT_ID)" 2>/dev/null || true)
  if [[ ${#bill_list[@]} -eq 1 && -n "${bill_list[0]}" ]]; then
    BILLING_ACCOUNT="${bill_list[0]}"
    echo "Billing Account automatically retrieved: ${BILLING_ACCOUNT}"
  elif [[ "${AUTO_CONFIRM}" == "true" ]]; then
    echo "Error: could not uniquely determine Billing Account under --yes; pass --billing-account." >&2
    exit 1
  else
    echo "Could not uniquely determine an open Billing Account (found ${#bill_list[@]})."
    read -r -p "Please enter your Billing Account ID (XXXXXX-XXXXXX-XXXXXX): " BILLING_ACCOUNT
  fi
fi

echo "*********************************************************"
echo "  DPF Layer-0 Workspace Bootstrap (New GCP Project)"
echo "  gcp_account_name : ${gcp_account_name}"
echo "  org_id           : ${ORG_ID:-<folder-parent>}"
echo "  folder_id        : ${FOLDER_ID:-<none>}"
echo "  billing_account  : ${BILLING_ACCOUNT}"
echo "  base_project_id  : ${PROJECT_ID} (random_suffix=${APPEND_RANDOM})"
echo "  dataform_repo    : ${DATAFORM_REPO}"
echo "  region           : ${REGION}"
echo "  business_timezone: ${TIMEZONE}"
echo "  presentation_url : ${PRESENTATION_SERVER_URL:-<local-only>}"
echo "*********************************************************"

if [[ "${AUTO_CONFIRM}" != "true" ]]; then
  read -r -p "Press [Enter] to provision this DPF environment, or Ctrl+C to cancel..."
fi

export TF_LOG=INFO
export TF_LOG_PATH="${REPO_ROOT}/bootstrap/tf.log"

pushd "${REPO_ROOT}/bootstrap/terraform" >/dev/null

terraform init
terraform validate

start_ts=$(date)
set +e
terraform apply -auto-approve \
  -var="gcp_account_name=${gcp_account_name}" \
  -var="org_id=${ORG_ID}" \
  -var="folder_id=${FOLDER_ID}" \
  -var="billing_account=${BILLING_ACCOUNT}" \
  -var="project_id=${PROJECT_ID}" \
  -var="append_random_suffix=${APPEND_RANDOM}" \
  -var="region=${REGION}" \
  -var="business_timezone=${TIMEZONE}" \
  -var="default_dataform_repository=${DATAFORM_REPO}" \
  -var="relax_domain_org_policy=${RELAX_DOMAIN_POLICY}"
tf_exit=$?
set -e
stop_ts=$(date)

echo ""
echo "Terraform start : ${start_ts}"
echo "Terraform finish: ${stop_ts}"

if [[ ${tf_exit} -eq 0 ]]; then
  terraform output -json > tf-output.json
  state_bucket=$(terraform output -raw terraform_output_bucket 2>/dev/null || true)
  if [[ -n "${state_bucket}" && "${state_bucket}" != *"Error"* ]]; then
    echo "==> Backing up tf-output.json and terraform.tfstate to gs://${state_bucket}/terraform/ ..."
    gcloud storage cp tf-output.json "gs://${state_bucket}/terraform/output/tf-output.json"
    gcloud storage cp terraform.tfstate "gs://${state_bucket}/terraform/state/terraform.tfstate"
  fi
  popd >/dev/null

  echo "==> Hydrating DPF workspace configuration..."
  hydrate_args=("${REPO_ROOT}/bootstrap/terraform/tf-output.json")
  if [[ "${PRESENTATION_URL_SET}" == "true" ]]; then
    hydrate_args+=(--presentation-server-url "${PRESENTATION_SERVER_URL}")
  fi
  if [[ "${FHD_URL_SET}" == "true" ]]; then
    hydrate_args+=(--fhd-server-url "${FHD_SERVER_URL}")
  fi
  python3 "${REPO_ROOT}/bootstrap/hydrate_workspace.py" "${hydrate_args[@]}"

  echo "*********************************************************"
  echo "  DPF Layer-0 Bootstrap Complete!"
  echo "  Next steps:"
  echo "    1. dpf check --all --gate G3"
  echo "    2. Build your first product or deploy examples/sales_performance"
  echo "*********************************************************"
else
  popd >/dev/null
  echo "Terraform exited with code ${tf_exit}. Inspect bootstrap/tf.log for details." >&2
  exit ${tf_exit}
fi
