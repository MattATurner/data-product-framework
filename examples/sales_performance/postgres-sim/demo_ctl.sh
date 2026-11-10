#!/usr/bin/env bash
# Start/stop & showcase controller for the PostgreSQL 16 OLTP simulator + 15-minute extractor.
# Supports three execution targets from the exact same codebase:
#   --target docker   Local or Google Cloud Shell Docker (postgres:16-alpine, 85 MB)
#   --target sqlite   Zero-Docker instant follow-along (Python stdlib sqlite3 WAL)
#   --target gce      Start/stop GCE COS appliance (no public IP, Cloud NAT + IAP, 4h auto-stop TTL)

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTRACT_DIR="$(cd "${HERE}/../extract" && pwd)"
REPO_ROOT="$(cd "${HERE}/../../.." && pwd)"

TARGET="${DPF_DEMO_TARGET:-auto}"
PROJECT="${DPF_DEMO_PROJECT:-data-products-deploy}"
ZONE="${DPF_DEMO_ZONE:-us-central1-a}"
REGION="${ZONE%-*}"
VM_NAME="${DPF_DEMO_VM:-pg-onprem-sim}"
NETWORK="${DPF_DEMO_NETWORK:-dpf-onprem-sim-net}"
SQLITE_DB="${HERE}/sales_erp.sqlite"

export PGUSER="${PGUSER:-sales_app}"
export PGPASSWORD="${PGPASSWORD:-sales_demo_pw}"
export PGDATABASE="${PGDATABASE:-sales_erp}"
export PGPORT="${PGPORT:-5432}"

# Parse global flags anywhere on the command line
ARGS=()
RUN_EXTRACT=false
DRY_RUN=false
RESET_BQ=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)   TARGET="$2"; shift 2 ;;
    --project)  PROJECT="$2"; shift 2 ;;
    --zone)     ZONE="$2"; REGION="${ZONE%-*}"; shift 2 ;;
    --vm)       VM_NAME="$2"; shift 2 ;;
    --extract)  RUN_EXTRACT=true; shift ;;
    --dry-run)  DRY_RUN=true; shift ;;
    --with-bigquery) RESET_BQ=true; shift ;;
    *)          ARGS+=("$1"); shift ;;
  esac
done

ACTION="${ARGS[0]:-help}"
STEP_ARG="${ARGS[1]:-}"

resolve_target() {
  if [[ "${TARGET}" != "auto" ]]; then
    echo "${TARGET}"
    return
  fi
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo "docker"
  else
    echo "sqlite"
  fi
}

MODE="$(resolve_target)"
PY_BIN="${REPO_ROOT}/.venv/bin/python"
[[ -x "${PY_BIN}" ]] || PY_BIN="python3"

gce_ssh() {
  gcloud compute ssh "${VM_NAME}" \
    --project="${PROJECT}" \
    --zone="${ZONE}" \
    --tunnel-through-iap \
    --quiet \
    --command="$1"
}

provision_gce() {
  echo "==> Provisioning isolated 'on-prem' PostgreSQL 16 appliance (${VM_NAME}) in ${PROJECT} (${ZONE})..."
  gcloud services enable compute.googleapis.com iap.googleapis.com iam.googleapis.com bigquery.googleapis.com dataform.googleapis.com \
    --project="${PROJECT}" --quiet

  local sa_name="dpf-pg-extractor"
  local sa_email="${sa_name}@${PROJECT}.iam.gserviceaccount.com"
  if ! gcloud iam service-accounts describe "${sa_email}" --project="${PROJECT}" >/dev/null 2>&1; then
    gcloud iam service-accounts create "${sa_name}" \
      --project="${PROJECT}" \
      --display-name="DPF Outbound PostgreSQL Watermark Extractor (ADR-015)" \
      --quiet
    sleep 4
  fi
  for role in roles/bigquery.jobUser roles/bigquery.dataEditor roles/logging.logWriter; do
    gcloud projects add-iam-policy-binding "${PROJECT}" \
      --member="serviceAccount:${sa_email}" \
      --role="${role}" \
      --condition=None \
      --quiet >/dev/null
  done

  if ! gcloud compute networks describe "${NETWORK}" --project="${PROJECT}" >/dev/null 2>&1; then
    gcloud compute networks create "${NETWORK}" --project="${PROJECT}" --subnet-mode=custom --quiet
  fi
  if ! gcloud compute networks subnets describe "${NETWORK}-${REGION}" --project="${PROJECT}" --region="${REGION}" >/dev/null 2>&1; then
    # Private Google Access only (zero public IP, zero Cloud NAT -> $0.00/hr idle networking, true ADR-015 isolation)
    gcloud compute networks subnets create "${NETWORK}-${REGION}" \
      --project="${PROJECT}" --network="${NETWORK}" --region="${REGION}" \
      --range="10.42.0.0/24" --enable-private-ip-google-access --quiet
  fi
  if ! gcloud compute firewall-rules describe "${NETWORK}-allow-iap" --project="${PROJECT}" >/dev/null 2>&1; then
    gcloud compute firewall-rules create "${NETWORK}-allow-iap" \
      --project="${PROJECT}" --network="${NETWORK}" \
      --direction=INGRESS --action=ALLOW --rules=tcp:22,tcp:5432 \
      --source-ranges=35.235.240.0/20 --quiet
  fi

  local startup_script
  startup_script=$(cat <<'EOS'
#!/bin/bash
set -e
# 4-hour automatic safety shutoff so the showcase VM never bills overnight
systemd-run --unit=dpf-autostop --on-active=4h /sbin/poweroff 2>/dev/null || true

mkdir -p /var/lib/dpf-pg/app

# Pull via mirror.gcr.io over Private Google Access (works with zero public internet / NAT)
if ! docker ps -a --format '{{.Names}}' | grep -qx dpf-pg-onprem-sim; then
  docker volume create dpf-pg-data >/dev/null
  docker run -d \
    --name dpf-pg-onprem-sim \
    --restart unless-stopped \
    -e POSTGRES_DB=sales_erp \
    -e POSTGRES_USER=sales_app \
    -e POSTGRES_PASSWORD=sales_demo_pw \
    -e TZ=UTC \
    -p 127.0.0.1:5432:5432 \
    -v dpf-pg-data:/var/lib/postgresql/data \
    mirror.gcr.io/library/postgres:16-alpine
else
  docker start dpf-pg-onprem-sim || true
fi
docker pull -q mirror.gcr.io/library/python:3.12-slim >/dev/null 2>&1 || true
EOS
)

  if ! gcloud compute instances describe "${VM_NAME}" --project="${PROJECT}" --zone="${ZONE}" >/dev/null 2>&1; then
    local tmp_startup
    tmp_startup="$(mktemp)"
    printf "%s\n" "${startup_script}" > "${tmp_startup}"
    gcloud compute instances create "${VM_NAME}" \
      --project="${PROJECT}" \
      --zone="${ZONE}" \
      --machine-type=e2-small \
      --network="${NETWORK}" \
      --subnet="${NETWORK}-${REGION}" \
      --no-address \
      --service-account="${sa_email}" \
      --scopes=https://www.googleapis.com/auth/cloud-platform \
      --image-family=cos-stable \
      --image-project=cos-cloud \
      --boot-disk-size=20GB \
      --shielded-secure-boot \
      --shielded-vtpm \
      --shielded-integrity-monitoring \
      --metadata-from-file=startup-script="${tmp_startup}" \
      --labels=purpose=dpf-postgres-sim \
      --quiet
    rm -f "${tmp_startup}"
  fi

  echo "==> Waiting for IAP SSH & PostgreSQL 16 container on ${VM_NAME}..."
  for _ in $(seq 1 30); do
    if gce_ssh "sudo docker exec dpf-pg-onprem-sim pg_isready -U sales_app -d sales_erp" >/dev/null 2>&1; then
      break
    fi
    sleep 3
  done

  echo "==> Syncing simulator, 15-minute watermark extractor, contracts & Linux wheels to ${VM_NAME}..."
  local stage_dir bundle
  stage_dir="$(mktemp -d)"
  bundle="$(mktemp --suffix=.tar.gz)"
  mkdir -p "${stage_dir}/app" "${stage_dir}/site-packages"
  tar -cf - -C "${REPO_ROOT}" \
    examples/sales_performance/postgres-sim/schema.sql \
    examples/sales_performance/postgres-sim/oltp_simulator.py \
    examples/sales_performance/extract/extract_postgres.py \
    examples/sales_performance/extract/config.yaml \
    framework/contracts | tar -xf - -C "${stage_dir}/app"

  if command -v uv >/dev/null 2>&1; then
    uv pip install --no-config --default-index https://pypi.org/simple --quiet --target "${stage_dir}/site-packages" \
      --python-platform x86_64-unknown-linux-gnu --python-version 3.12 \
      'psycopg[binary]' google-cloud-bigquery pyyaml jsonschema referencing
  elif [[ -x "${HOME}/.local/bin/uv" ]]; then
    "${HOME}/.local/bin/uv" pip install --no-config --default-index https://pypi.org/simple --quiet --target "${stage_dir}/site-packages" \
      --python-platform x86_64-unknown-linux-gnu --python-version 3.12 \
      'psycopg[binary]' google-cloud-bigquery pyyaml jsonschema referencing
  else
    python3 -m pip install --index-url https://pypi.org/simple --quiet --target "${stage_dir}/site-packages" \
      --platform manylinux2014_x86_64 --python-version 3.12 --only-binary=:all: \
      'psycopg[binary]' google-cloud-bigquery pyyaml jsonschema referencing
  fi

  tar -czf "${bundle}" -C "${stage_dir}" app site-packages
  rm -rf "${stage_dir}"

  gcloud compute scp "${bundle}" "${VM_NAME}:/tmp/dpf_sim_bundle.tar.gz" \
    --project="${PROJECT}" --zone="${ZONE}" --tunnel-through-iap --quiet
  rm -f "${bundle}"

  gce_ssh "
    sudo mkdir -p /var/lib/dpf-pg/app && sudo chown -R \$USER:\$USER /var/lib/dpf-pg
    rm -rf /var/lib/dpf-pg/app /var/lib/dpf-pg/site-packages
    tar -xzf /tmp/dpf_sim_bundle.tar.gz -C /var/lib/dpf-pg
    rm -f /tmp/dpf_sim_bundle.tar.gz
    sudo docker pull -q mirror.gcr.io/library/python:3.12-slim >/dev/null
    cat <<'EOD' > /var/lib/dpf-pg/Dockerfile.ext
FROM mirror.gcr.io/library/python:3.12-slim
COPY site-packages /usr/local/lib/python3.12/site-packages
EOD
    sudo docker build -q -t dpf-extractor:py312 -f /var/lib/dpf-pg/Dockerfile.ext /var/lib/dpf-pg >/dev/null
    rm -rf /var/lib/dpf-pg/site-packages /var/lib/dpf-pg/Dockerfile.ext
    sudo docker exec -i dpf-pg-onprem-sim psql -U sales_app -d sales_erp < /var/lib/dpf-pg/app/examples/sales_performance/postgres-sim/schema.sql >/dev/null
    sudo tee /etc/systemd/system/dpf-extract.service >/dev/null <<'EOSVC'
[Unit]
Description=DPF 15-Minute Outbound PostgreSQL Watermark Extractor
After=docker.service

[Service]
Type=oneshot
ExecStart=/usr/bin/docker run --rm --network=host -e PGUSER=sales_app -e PGPASSWORD=sales_demo_pw -e DPF_CONTRACTS_DIR=/app/framework/contracts -v /var/lib/dpf-pg/app:/app:ro dpf-extractor:py312 python3 /app/examples/sales_performance/extract/extract_postgres.py --project=${PROJECT}
EOSVC
    sudo tee /etc/systemd/system/dpf-extract.timer >/dev/null <<'EOTMR'
[Unit]
Description=Run DPF Outbound Watermark Extract Every 15 Minutes

[Timer]
OnCalendar=*:0/15
Persistent=true

[Install]
WantedBy=timers.target
EOTMR
    sudo systemctl daemon-reload
    sudo systemctl enable --now dpf-extract.timer
  "
  echo "✅ ${VM_NAME} is online (PostgreSQL 16 + Private Google Access + 15-min timer + 4-hour auto-stop active)."
}

run_gce_py() {
  local script_rel="$1"; shift
  gce_ssh "sudo docker run --rm --network=host \
    -e PGUSER=sales_app -e PGPASSWORD=sales_demo_pw \
    -e DPF_CONTRACTS_DIR=/app/framework/contracts \
    -v /var/lib/dpf-pg/app:/app:ro \
    dpf-extractor:py312 python3 /app/${script_rel} $*"
}

case "${ACTION}" in
  provision)
    provision_gce
    ;;

  start|up)
    if [[ "${MODE}" == "gce" ]]; then
      if ! gcloud compute instances describe "${VM_NAME}" --project="${PROJECT}" --zone="${ZONE}" >/dev/null 2>&1; then
        provision_gce
      else
        echo "==> Starting ${VM_NAME} in ${PROJECT} (${ZONE})..."
        gcloud compute instances start "${VM_NAME}" --project="${PROJECT}" --zone="${ZONE}" --quiet
        for _ in $(seq 1 20); do
          if gce_ssh "sudo docker exec dpf-pg-onprem-sim pg_isready -U sales_app -d sales_erp" >/dev/null 2>&1; then
            break
          fi
          sleep 2
        done
        echo "✅ ${VM_NAME} RUNNING (PostgreSQL 16 ready; 15-min extract timer & 4h auto-stop active)."
      fi
    elif [[ "${MODE}" == "docker" ]]; then
      docker compose -f "${HERE}/docker-compose.yml" up -d --wait
      echo "✅ Local PostgreSQL 16 container running on 127.0.0.1:${PGPORT}."
    else
      "${PY_BIN}" "${HERE}/oltp_simulator.py" init --dsn "sqlite:///${SQLITE_DB}"
      echo "✅ Zero-Docker SQLite WAL database initialised at ${SQLITE_DB}."
    fi
    ;;

  stop|down)
    if [[ "${MODE}" == "gce" ]]; then
      echo "==> Cleanly flushing PostgreSQL and stopping ${VM_NAME}..."
      gce_ssh "sudo docker stop dpf-pg-onprem-sim || true" >/dev/null 2>&1 || true
      gcloud compute instances stop "${VM_NAME}" --project="${PROJECT}" --zone="${ZONE}" --quiet
      echo "✅ ${VM_NAME} TERMINATED (compute billing = \$0.00)."
    elif [[ "${MODE}" == "docker" ]]; then
      docker compose -f "${HERE}/docker-compose.yml" stop
      echo "✅ Local PostgreSQL 16 container stopped."
    else
      echo "ℹ️  SQLite WAL mode uses ${SQLITE_DB} (no background daemon to stop)."
    fi
    ;;

  status)
    if [[ "${MODE}" == "gce" ]]; then
      vm_status="$(gcloud compute instances describe "${VM_NAME}" --project="${PROJECT}" --zone="${ZONE}" --format='value(status)' 2>/dev/null || echo 'NOT_CREATED')"
      echo "GCE Appliance (${VM_NAME} in ${PROJECT}): ${vm_status}"
      if [[ "${vm_status}" == "RUNNING" ]]; then
        run_gce_py "examples/sales_performance/postgres-sim/oltp_simulator.py" status
      fi
    elif [[ "${MODE}" == "docker" ]]; then
      "${PY_BIN}" "${HERE}/oltp_simulator.py" status --dsn "host=127.0.0.1 port=${PGPORT} dbname=${PGDATABASE}"
    else
      "${PY_BIN}" "${HERE}/oltp_simulator.py" status --dsn "sqlite:///${SQLITE_DB}"
    fi
    ;;

  reset)
    if [[ "${MODE}" == "gce" ]]; then
      run_gce_py "examples/sales_performance/postgres-sim/oltp_simulator.py" reset
    elif [[ "${MODE}" == "docker" ]]; then
      "${PY_BIN}" "${HERE}/oltp_simulator.py" reset --dsn "host=127.0.0.1 port=${PGPORT} dbname=${PGDATABASE}"
    else
      rm -f "${SQLITE_DB}" "${SQLITE_DB}-wal" "${SQLITE_DB}-shm"
      "${PY_BIN}" "${HERE}/oltp_simulator.py" init --dsn "sqlite:///${SQLITE_DB}"
    fi
    if [[ "${RESET_BQ}" == "true" ]]; then
      echo "==> Resetting BigQuery raw_pg_local and dpf_control tables in ${PROJECT}..."
      for ds in raw_pg_local dpf_control; do
        bq --location=us-central1 rm -r -f -d "${PROJECT}:${ds}" >/dev/null 2>&1 || true
        bq --location=us-central1 mk -d "${PROJECT}:${ds}" >/dev/null
      done
    fi
    ;;

  step)
    if [[ -z "${STEP_ARG}" ]]; then
      echo "Usage: $0 step <1a|1b|1c|1|2|3|4|5> [--extract] [--target gce|docker|sqlite]" >&2
      exit 2
    fi
    if [[ "${MODE}" == "gce" ]]; then
      run_gce_py "examples/sales_performance/postgres-sim/oltp_simulator.py" step "${STEP_ARG}"
      if [[ "${RUN_EXTRACT}" == "true" ]]; then
        extra_flag=""
        [[ "${DRY_RUN}" == "true" ]] && extra_flag="--dry-run"
        run_gce_py "examples/sales_performance/extract/extract_postgres.py" "--project=${PROJECT}" ${extra_flag}
      fi
    elif [[ "${MODE}" == "docker" ]]; then
      dsn="host=127.0.0.1 port=${PGPORT} dbname=${PGDATABASE}"
      "${PY_BIN}" "${HERE}/oltp_simulator.py" step "${STEP_ARG}" --dsn "${dsn}"
      if [[ "${RUN_EXTRACT}" == "true" ]]; then
        extra_flag=""
        [[ "${DRY_RUN}" == "true" ]] && extra_flag="--dry-run"
        "${PY_BIN}" "${EXTRACT_DIR}/extract_postgres.py" --dsn "${dsn}" --project "${PROJECT}" ${extra_flag}
      fi
    else
      dsn="sqlite:///${SQLITE_DB}"
      "${PY_BIN}" "${HERE}/oltp_simulator.py" step "${STEP_ARG}" --dsn "${dsn}"
      if [[ "${RUN_EXTRACT}" == "true" ]]; then
        extra_flag=""
        [[ "${DRY_RUN}" == "true" ]] && extra_flag="--dry-run"
        "${PY_BIN}" "${EXTRACT_DIR}/extract_postgres.py" --dsn "${dsn}" --project "${PROJECT}" ${extra_flag}
      fi
    fi
    ;;

  extract)
    extra_args=()
    [[ -n "${STEP_ARG}" ]] && extra_args+=("${STEP_ARG}")
    [[ "${DRY_RUN}" == "true" ]] && extra_args+=("--dry-run")
    if [[ "${MODE}" == "gce" ]]; then
      run_gce_py "examples/sales_performance/extract/extract_postgres.py" "--project=${PROJECT}" "${extra_args[@]}"
    elif [[ "${MODE}" == "docker" ]]; then
      "${PY_BIN}" "${EXTRACT_DIR}/extract_postgres.py" --dsn "host=127.0.0.1 port=${PGPORT} dbname=${PGDATABASE}" --project "${PROJECT}" "${extra_args[@]}"
    else
      "${PY_BIN}" "${EXTRACT_DIR}/extract_postgres.py" --dsn "sqlite:///${SQLITE_DB}" --project "${PROJECT}" "${extra_args[@]}"
    fi
    ;;

  psql)
    if [[ "${MODE}" == "gce" ]]; then
      gcloud compute ssh "${VM_NAME}" --project="${PROJECT}" --zone="${ZONE}" --tunnel-through-iap \
        --command="sudo docker exec -it dpf-pg-onprem-sim psql -U sales_app -d sales_erp"
    elif [[ "${MODE}" == "docker" ]]; then
      docker exec -it dpf-pg-onprem-sim psql -U "${PGUSER}" -d "${PGDATABASE}"
    else
      echo "SQLite mode active; inspect with python3 -c \"import sqlite3; ...\" on ${SQLITE_DB}"
    fi
    ;;

  *)
    cat <<EOF
Usage: $0 <command> [--target docker|sqlite|gce] [--project <gcp-project>]

Commands:
  start | up                   Start PostgreSQL 16 simulator (or GCE pg-onprem-sim VM)
  stop  | down                 Stop PostgreSQL 16 simulator (powers off GCE VM -> \$0 compute)
  status                       Show DB status, table row counts & current C-001 / SO-1005 state
  reset [--with-bigquery]      Reset source OLTP tables (and optionally raw/control BQ datasets)
  step <1a|1b|1c|1|2|3|4|5> [--extract] [--dry-run]
                               Apply a transactional OLTP story beat (and optionally run extract)
  extract [entity] [--dry-run] Run outbound 15-minute watermark extractor immediately
  psql                         Open interactive psql shell into sales_erp
EOF
    ;;
esac
