---
id: ADR-003
title: Orchestrator
status: accepted
date: '2026-09-09'
scope: platform
decides: orchestration
---

# ADR-003: Orchestrator

## Decision

Dataform release and workflow configurations are the default orchestrator for pure-SQL chains. The manifest (`orchestration.engine`) also supports Cloud Composer (`composer`), Cloud Run Jobs (`cloud_run_jobs`), Cloud Workflows (`cloud_workflows`), Dagster (`dagster`), and Prefect (`prefect`) when teams standardise on an external scheduler or serverless container runner. When Dataform is paired with an external scheduler (`composer`, `dagster`, `prefect`), Terraform still provisions the Dataform release configuration to compile the repository while omitting Dataform's internal cron workflow configs so only one scheduler triggers runs.

## Consequences

Orchestration resources and DAGs/flows are generated deterministically from `orchestration.schedules` in the manifest.
