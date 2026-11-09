---
name: render-lookml-artefacts
description: Render LookML project manifests, connections, views, symmetric-aggregate primary keys, explores, aggregate awareness tables and Stephen Few LookML dashboards deterministically from the semantic layer specification.
metadata:
  dpf:
    skill_id: render-lookml-artefacts
    stage: render
    scope: product
    selects_when:
      product.semantic_layer.targets: lookml
    implements: generate-artefacts
    consumes:
    - semantic-model.v1
    - product-manifest.v1
    produces:
    - semantic-layer.v1
    tool_tier: 4
    tool: dpf-local
    inspection_tool: looker-mcp
    adr: ADR-018
    gcp:
    - BigQuery
    - Looker
    needs:
    - artefact_generation
---

# Render LookML artefacts

```bash
dpf generate <product>                     # writes generated/<product>/semantic_layer/lookml/
dpf generate <product> --env prod          # retargets @{GCP_PROJECT} in manifest.lkml
dpf proto import-looker <id> --from <dir>  # imports hand-authored LookML into prototype status
```

| Output | Contents |
|---|---|
| `semantic_layer/lookml/manifest.lkml` | project name, optional `local_dependency` hub import, `GCP_PROJECT` and `DATASET_*` constants |
| `semantic_layer/lookml/<product>.model.lkml` | connection, datagroup cache policy, `access_grant` mappings, view/explore/dashboard includes |
| `semantic_layer/lookml/views/*.view.lkml` | one view (or `+view` refinement) per semantic cube with deterministic `primary_key: yes` |
| `semantic_layer/lookml/explores/*.explore.lkml` | `many_to_one` surrogate-key joins, partition filters and `aggregate_table` blocks |
| `semantic_layer/lookml/dashboards/*.dashboard.lookml` | Looker newspaper-layout YAML dashboards enforcing Stephen Few visual rules |
| `semantic_layer/lookml/GEMINI.md` | agent guardrails for Looker IDE and `looker-mcp` sessions |

Never introduce Persistent Derived Tables (`derived_table` with `sql_trigger_value` or `datagroup_trigger`)
inside LookML views unless `looker.allow_pdt: true` is paired with an accepted ADR (`decides: semantic_layer`).
