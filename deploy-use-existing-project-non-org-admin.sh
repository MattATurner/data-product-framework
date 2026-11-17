#!/usr/bin/env bash
####################################################################################
# Copyright 2026 Google LLC — Apache License 2.0
#
# Data Product Framework (DPF) — Layer-0 Bootstrap Into an Existing Customer Project
# (Non-Org-Admin / Pre-Provisioned Enterprise GCP Project)
#
# USAGE:
#   ./deploy-use-existing-project-non-org-admin.sh \
#     --project-id my-existing-project \
#     --region australia-southeast1 \
#     --timezone Pacific/Auckland
####################################################################################

set -uo pipefail

PROJECT_ID=""
PROJECT_NUMBER=""
GCP_ACCOUNT=""
REGION="us-central1"
TIMEZONE="Australia/Perth"
DATAFORM_REPO="sales-performance"
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
    --project-id)              PROJECT_ID="$2"; shift 2 ;;
    --project-number)          PROJECT_NUMBER="$2"; shift 2 ;;
    --account)                 GCP_ACCOUNT="$2"; shift 2 ;;
    --region)                  REGION="$2"; shift 2 ;;
    --timezone)                TIMEZONE="$2"; shift 2 ;;
    --dataform-repo)           DATAFORM_REPO="$2"; shift 2 ;;
    --presentation-server-url) PRESENTATION_SERVER_URL="$2"; PRESENTATION_URL_SET="true"; shift 2 ;;
    --fhd-server-url)          FHD_SERVER_URL="$2"; FHD_URL_SET="true"; shift 2 ;;
    --clean-examples)          CLEAN_EXAMPLES="true"; shift ;;
    --yes|-y)                  AUTO_CONFIRM="true"; shift ;;
    *) echo "Unknown option: $1"; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

if [[ "${CLEAN_EXAMPLES}" == "true" ]]; then
  echo "==> Stripping worked example material to create a clean customer workspace..."
  bash "${REPO_ROOT}/clean-up.sh" --strip-examples
fi

if [[ "${AUTO_CONFIRM}" != "true" && "${PRESENTATION_URL_SET}" != "true" ]]; then
  existing_pres_url=$(python3 -c 'import json,sys,pathlib; p=pathlib.Path(sys.argv[1]); print((json.loads(p.read_text()).get("presentation_server_url") or "") if p.is_file() else "")' "${REPO_ROOT}/agent-config.json" 2>/dev/null || true)
  if [[ -n "${existing_pres_url}" ]]; then
    PRESENTATION_SERVER_URL="${existing_pres_url}"
  else
    read -r -p "Optional Presentation Server URL for hosting HTML decks/cockpits (e.g. https://...a.run.app, or press Enter for local-only): " PRESENTATION_SERVER_URL
    PRESENTATION_URL_SET="true"
  fi
fi

if [[ -z "${GCP_ACCOUNT}" ]]; then
  GCP_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -n 1)
fi

if [[ -z "${PROJECT_ID}" ]]; then
  PROJECT_ID=$(gcloud config get-value project 2>/dev/null || true)
fi

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  read -r -p "Enter your existing GCP Project ID: " PROJECT_ID
fi

if [[ -z "${PROJECT_NUMBER}" ]]; then
  PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)" 2>/dev/null || true)
  if [[ -z "${PROJECT_NUMBER}" ]]; then
    read -r -p "Enter the 12-digit GCP Project Number for ${PROJECT_ID}: " PROJECT_NUMBER
  fi
fi

echo "*********************************************************"
echo "  DPF Layer-0 Bootstrap (Existing Project / Non-Org-Admin)"
echo "  gcp_account_name : ${GCP_ACCOUNT}"
echo "  project_id       : ${PROJECT_ID}"
echo "  project_number   : ${PROJECT_NUMBER}"
echo "  region           : ${REGION}"
echo "  business_timezone: ${TIMEZONE}"
echo "  presentation_url : ${PRESENTATION_SERVER_URL:-<local-only>}"
echo "*********************************************************"

pushd "${REPO_ROOT}/bootstrap/terraform" >/dev/null || exit 1

terraform init
terraform validate

# Passing org_id="0" and a non-empty project_number signals Terraform to skip project creation and org policies.
terraform apply \
  -var="gcp_account_name=${GCP_ACCOUNT}" \
  -var="project_id=${PROJECT_ID}" \
  -var="project_number=${PROJECT_NUMBER}" \
  -var="append_random_suffix=false" \
  -var="org_id=0" \
  -var="region=${REGION}" \
  -var="business_timezone=${TIMEZONE}" \
  -var="default_dataform_repository=${DATAFORM_REPO}"
tf_exit=$?

if [[ ${tf_exit} -eq 0 ]]; then
  terraform output -json > tf-output.json
  state_bucket=$(terraform output -raw terraform_output_bucket 2>/dev/null || true)
  if [[ -n "${state_bucket}" && "${state_bucket}" != *"Error"* ]]; then
    gcloud storage cp tf-output.json "gs://${state_bucket}/terraform/output/tf-output.json"
    gcloud storage cp terraform.tfstate "gs://${state_bucket}/terraform/state/terraform.tfstate"
  fi
  popd >/dev/null || exit 1

  hydrate_args=("${REPO_ROOT}/bootstrap/terraform/tf-output.json")
  if [[ "${PRESENTATION_URL_SET}" == "true" ]]; then
    hydrate_args+=(--presentation-server-url "${PRESENTATION_SERVER_URL}")
  fi
  if [[ "${FHD_URL_SET}" == "true" ]]; then
    hydrate_args+=(--fhd-server-url "${FHD_SERVER_URL}")
  fi
  python3 "${REPO_ROOT}/bootstrap/hydrate_workspace.py" "${hydrate_args[@]}"
  echo "Done."
else
  popd >/dev/null || exit 1
  return ${tf_exit} 2>/dev/null || exit ${tf_exit}
fi
