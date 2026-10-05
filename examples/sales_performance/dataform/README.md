# Dataform — sales_performance

There is no hand-written SQLX here any more. The Dataform project is **generated** from the
manifest, the authored SQL bodies and the methodology packs:

```bash
dpf generate sales_performance          # writes generated/sales_performance/dataform/
```

| Where | What |
|---|---|
| `generated/sales_performance/dataform/` | the project to push to the Dataform repository (gitignored, regenerate at will) |
| `tests/golden/sales_performance/dataform/` | the reviewed golden copy; `dpf generate --check` fails if a build differs |
| `products/sales_performance/sql/` | the authored SQL bodies (business logic only, no config) |
| `products/sales_performance/product.yaml` | grain, keys, history, quality rules, schedules, governance |

The generated project contains 4 raw declarations, 18 models and helper views (staging
candidates, history and reject views; Type 2 dimensions; the transaction fact; gold views)
and 36 assertions: grain, not-null keys, SCD integrity, late-arriving members, the R-11
reject gate and the automated acceptance tests.

**Why generated, not written:** the earlier hand-written SQLX drifted from the TDD. It
silently dropped the rows R-11 says must stop publication, its gold grain did not match the
manifest, its `dim_customer` assertion tested a different property from the declared grain,
and the R-13 partner extract had no model. Generating from the manifest makes the TDD, the
SQL and the tests one artefact, and the golden copy makes every change reviewable as a diff.

To deploy, push the generated tree to the default branch of the repository named in the
Terraform variable `dataform_repository`; the release configuration compiles it hourly and
one workflow configuration per schedule (`hourly`, `monthly`) runs the tagged actions. To
build by hand: `cd generated/sales_performance/dataform && npx @dataform/cli@3 run`.

The same product renders for dbt with `dpf generate sales_performance --engine dbt`
(`generated/sales_performance--dbt/dbt/`).
