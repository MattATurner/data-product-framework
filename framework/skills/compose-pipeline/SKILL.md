---
name: compose-pipeline
description: Select the skills for each source and model from their selects_when conditions, type-check
  every contract handoff and engine support, and emit the ordered pipeline DAG. Use after G1 and before
  generating artefacts.
metadata:
  dpf:
    skill_id: compose-pipeline
    stage: design
    scope: product
    implements: compose-pipeline
    consumes:
    - product-manifest.v1
    produces: []
    tool_tier: 4
    tool: dpf-local
    needs:
    - artefact_generation
---

# Compose the pipeline

```bash
dpf compose <product>          # writes generated/<product>/dag.json and dag.md
```

## How selection works

Every skill's `metadata.dpf.selects_when` is matched against each instance in the
manifest: products, sources (`source.engine`, `source.capture_mode`) and models
(`model.role`, `layer.methodology`). All keys must match; list values mean "any of".
An Oracle watermark source selects `extract-rdbms-watermark`; a file drop selects
`extract-files-object-store`. Nothing is hard-coded.

## Checks

1. Exactly one skill per source per stage, and per model.
2. Each model's inputs (from its SQL body refs or its declared attributes) exist upstream.
3. Every edge type-checks: the producer's contract is in the consumer skill's `consumes`.
4. The layer engine's adapter implements the role, and the pack lists the engine for it.

## Must

- Fail with both contract ids named on a mismatch. Never generate a partial pipeline.
- Be deterministic: same manifest, same DAG.
