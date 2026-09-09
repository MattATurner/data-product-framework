---
skill_id: orchestrate-pipeline
implements: compose-pipeline
consumes: quality-policy.v1
produces: null
tool_tier: 4
tool: dataform_api
gcp: [Dataform workflow configs, Cloud Composer]
---

# Orchestrate

## Choosing

| Use | When |
|---|---|
| **Dataform release + workflow configs** | Pure BigQuery SQL chains |
| **Cloud Composer** | Non-BigQuery steps must be sequenced — Datastream state, Cloud Run extracts, catalog calls |
| **Workflows** | Trivial cases only |

## Must

- Set the cadence from the BRD's freshness answer, not from habit.
- Make every run idempotent; a re-run must not double-count.
- Honour the restatement window: rebuild only affected partitions.
- Stop the pipeline on a blocking quality failure — do not publish and warn.
