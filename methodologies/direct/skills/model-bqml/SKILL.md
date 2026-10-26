---
name: model-bqml
description: Train a BigQuery ML model (CREATE OR REPLACE MODEL) or produce batch predictions and forecasts
  (ML.PREDICT, ML.FORECAST) over staging or integration models. Use for roles ml_model and ml_prediction in a direct layer.
metadata:
  dpf:
    skill_id: direct/model-bqml
    stage: consume
    scope: model
    implements: model-consumption-layer
    methodology: direct
    consumes:
    - staging-model.v1
    - semantic-model.v1
    produces:
    - semantic-model.v1
    selects_when:
      model.role:
      - ml_model
      - ml_prediction
      layer.methodology: direct
    tool_tier: 4
    tool: dpf-local
    inspection_tool: bigquery-mcp
    needs:
    - artefact_generation
    gcp:
    - BigQuery
---

# Build BigQuery ML models and predictions

## Steps

1. For `role: ml_model`, set `materialisation: bqml_model` and declare `attributes.model_type`
   (for example `LOGISTIC_REG`, `BOOSTED_TREE_CLASSIFIER`, `ARIMA_PLUS`) and optional
   `attributes.evaluation` thresholds (`metric`, `min`, `max`).
2. Write the training `SELECT` query in `products/<product>/sql/<model>.sql` using `{{ ref('model') }}`
   for upstream staging or silver inputs; dpf wraps the query in `CREATE OR REPLACE MODEL ... OPTIONS(...) AS`.
3. For `role: ml_prediction`, write the inference query using `ML.PREDICT(MODEL {{ ref('ml_model') }}, ...)`
   or `ML.FORECAST(MODEL {{ ref('ml_model') }}, ...)` and materialise as `table` or `view`.

## Must not

- Train directly on raw tables; always train on deduplicated staging or integration models after reject gates.
