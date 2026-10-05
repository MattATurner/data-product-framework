# Orchestration — sales_performance (dbt)

dbt has no scheduler of its own. Run each schedule below from Cloud Composer, Cloud Run jobs or Workflows with the given cron, in the business timezone. `dbt build` runs every model's tests straight after the model and skips everything downstream of a failed blocking test; acceptance tests are excluded from scheduled runs.

| Schedule | Cron | Timezone | Command |
|---|---|---|---|
| `hourly` | `10 * * * *` | Australia/Perth | `dbt build --select tag:hourly --exclude tag:acceptance --vars '{policy_tag_pii_contact: <terraform output>}'` |
| `monthly` | `0 7 2 * *` | Australia/Perth | `dbt build --select tag:monthly --exclude tag:acceptance --vars '{policy_tag_pii_contact: <terraform output>}'` |

Acceptance (against the seeded fixture, never scheduled):

```bash
dbt build --exclude tag:acceptance --vars '{policy_tag_pii_contact: <terraform output>}'
dbt test --select tag:acceptance
```

Warn-level tests report but never skip downstream models.
