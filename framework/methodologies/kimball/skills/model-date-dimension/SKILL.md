---
name: model-date-dimension
description: Generate a calendar date dimension with one row per day between declared bounds, keyed YYYYMMDD,
  with month, quarter and weekday attributes. Use for role calendar in a kimball layer.
metadata:
  dpf:
    skill_id: kimball/model-date-dimension
    stage: integrate
    scope: model
    implements: model-integration-layer
    methodology: kimball
    role: calendar
    consumes: []
    produces:
    - semantic-model.v1
    selects_when:
      model.role: calendar
      layer.methodology: kimball
    tool_tier: 4
    tool: dpf-local
    needs:
    - artefact_generation
    gcp:
    - BigQuery
---

# Generate the date dimension

```yaml
- name: dim_date
  role: calendar
  grain_columns: [date_key]
  attributes: {start_date: "2020-01-01", end_date: "2030-12-31"}
```

Columns: `date_key` (INT64 YYYYMMDD), `calendar_date`, `calendar_year`,
`calendar_quarter`, `calendar_month`, `year_month` (YYYY-MM), `day_name`, `is_weekend`.
Generated, never sourced; it is still declared in the manifest so its grain is asserted
and facts can reference it.
