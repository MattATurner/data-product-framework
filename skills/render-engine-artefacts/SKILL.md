---
name: render-engine-artefacts
description: Render semantic models, staging models, the quality policy and the test specification into
  engine artefacts (Dataform or dbt), Terraform and observability policy, deterministically. Use after
  compose succeeds.
metadata:
  dpf:
    skill_id: render-engine-artefacts
    stage: render
    scope: product
    implements: generate-artefacts
    consumes:
    - semantic-model.v1
    - staging-model.v1
    - quality-policy.v1
    - test-spec.v1
    produces: []
    tool_tier: 4
    tool: dpf-local
    needs:
    - artefact_generation
---

# Render engine artefacts

```bash
dpf generate <product>            # writes generated/<product>/
dpf generate --all --check        # diff against tests/golden/ (CI)
```

| Output | Contents |
|---|---|
| `semantic/`, `staging/` | one contract instance per model |
| `dataform/` or `dbt/` | engine project from the layer engines |
| `terraform/` | datasets, policy tags and masking, sharing listing, workflow schedules, alerting |
| `observability/` | observability policy and data quality scan specs |
| `MANIFEST.json` | digest of every file plus the build digest evidence is bound to |

Never edit `generated/` by hand. Change the manifest, SQL bodies or packs and regenerate.
