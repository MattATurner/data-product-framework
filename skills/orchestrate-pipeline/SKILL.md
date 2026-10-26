---
name: orchestrate-pipeline
description: 'Schedule the generated pipeline from the manifest''s orchestration schedules: release and
  workflow configurations per schedule, blocking on failed checks, honouring the restatement window. Use
  when deploying a product.'
metadata:
  dpf:
    skill_id: orchestrate-pipeline
    stage: orchestrate
    scope: product
    implements: compose-pipeline
    consumes:
    - product-manifest.v1
    produces: []
    tool_tier: 4
    tool: terraform
    needs:
    - terraform_provisioning
    - dataform_workflow_invocation
    gcp:
    - Dataform
---

# Orchestrate

| Use (`orchestration.engine`) | When |
|---|---|
| `dataform` (default) | Pure BigQuery SQL chains via Dataform release and workflow configurations |
| `composer` | Cloud Composer (Airflow) DAGs in the product's business timezone |
| `cloud_run_jobs` | Serverless container execution (`google_cloud_run_v2_job` + Cloud Scheduler) |
| `cloud_workflows` | Serverless HTTP step orchestration (`google_workflows_workflow` + Cloud Scheduler) |
| `dagster` | Asset-centric orchestration (`ScheduleDefinition` + `Definitions`) |
| `prefect` | Python-native flow orchestration (`@flow` + `CronSchedule`) |

## Must

- Take cadence from the BRD's freshness answer via `orchestration.schedules`.
- Exclude acceptance tests (tag `acceptance`) from scheduled runs.
- Make every run idempotent and honour `quality.gate_behaviour` (`block` or `warn`) and any configured reject thresholds (`max_reject_pct`, `max_reject_rows`).
