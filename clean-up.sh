#!/usr/bin/env bash
####################################################################################
# Copyright 2026 Google LLC — Apache License 2.0
#
# Resets local Layer-0 Terraform state/cache files, or optionally strips worked
# example material in-place when starting a clean customer repository from the
# GitHub Template (--strip-examples).
####################################################################################

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
STRIP_EXAMPLES="false"

if [[ "${1:-}" == "--strip-examples" ]]; then
  STRIP_EXAMPLES="true"
fi

echo "==> Cleaning local Terraform cache and state files in bootstrap/terraform..."
rm -rf "${REPO_ROOT}/bootstrap/terraform/.terraform"
rm -f  "${REPO_ROOT}/bootstrap/terraform/.terraform.lock.hcl"
rm -f  "${REPO_ROOT}/bootstrap/terraform/terraform.tfstate"
rm -f  "${REPO_ROOT}/bootstrap/terraform/terraform.tfstate.backup"
rm -f  "${REPO_ROOT}/bootstrap/terraform/tf-output.json"
rm -f  "${REPO_ROOT}/bootstrap/tf.log"

if [[ "${STRIP_EXAMPLES}" == "true" ]]; then
  echo "==> Removing worked example products, golden fixtures, and demo decks for a clean customer repo..."
  rm -rf "${REPO_ROOT}/examples" \
         "${REPO_ROOT}/generated" \
         "${REPO_ROOT}/evidence" \
         "${REPO_ROOT}/docs/fhd" \
         "${REPO_ROOT}/docs/presentation" \
         "${REPO_ROOT}/docs/index.html" \
         "${REPO_ROOT}/docs/data-product-framework-plan.md"

  find "${REPO_ROOT}/openspec/specs/products" -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true
  find "${REPO_ROOT}/products" -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true
  find "${REPO_ROOT}/tests/golden" -mindepth 1 -maxdepth 1 ! -name "README.md" -exec rm -rf {} + 2>/dev/null || true

  mkdir -p "${REPO_ROOT}/openspec/specs/products" "${REPO_ROOT}/openspec/changes" "${REPO_ROOT}/products" "${REPO_ROOT}/tests/golden"
  touch "${REPO_ROOT}/openspec/specs/products/.gitkeep" \
        "${REPO_ROOT}/products/.gitkeep" \
        "${REPO_ROOT}/tests/golden/.gitkeep"
  echo "  ok | Clean customer workspace ready (run 'dpf check --all --gate G3' to verify)."
fi
