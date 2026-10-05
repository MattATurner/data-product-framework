---
name: monitor-data-product
description: 'Operate a published product against its observability policy: freshness inside the business
  calendar, volume, breaking schema drift and failed checks; alert, and open an OpenSpec change proposal
  on a breach.'
metadata:
  dpf:
    skill_id: monitor-data-product
    stage: monitor
    scope: product
    implements: monitor-data-product
    consumes:
    - observability-policy.v1
    - run-evidence.v1
    produces: []
    tool_tier: 4
    tool: dpf-local
    needs:
    - run_evaluation
    gcp:
    - Cloud Monitoring
    - Cloud Logging
---

# Monitor the data product

Two halves:

1. **Always on** (generated Terraform): log-based metrics and alert policies for failed
   builds, extract failures and breaking schema drift, plus scheduled freshness and volume
   checks that raise an error when the policy is breached.
2. **Evaluate and act**: collect run evidence (`run-evidence.v1`) and run

```bash
dpf monitor <product> --evidence run.json [--open-change]
```

Freshness is only judged inside the policy's business calendar. A breach with
`--open-change` scaffolds `openspec/changes/<date>-<product>-<kind>/` (proposal and tasks)
so the fix goes through the same spec-driven loop as any other change.
