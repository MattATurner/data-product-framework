# Engine adapters

Methodology packs emit `semantic-model.v1`. Engine adapters render that model into
executable artefacts. **Packs never emit engine-specific artefacts, and adapters never
make modelling decisions.** If either side starts knowing about the other, the plane has
leaked.

Each adapter declares what it can actually render in `adapter.yaml` (contract
`engine-adapter.v1`). A pack may list an engine in `supported_engines` for a role **only
if** the adapter lists that role in `implemented_roles`; `dpf validate` enforces this, and
`dpf compose` fails a product whose layer engine does not implement a role it uses.

| Engine | Status | Renders to | Generator |
|---|---|---|---|
| `dataform` | implemented (default) | SQLX tables, views, incremental tables, assertions, declarations | `dpf/generate/dataform.py` |
| `dbt` | implemented | models, sources, singular tests, `dbt_project.yml` | `dpf/generate/dbt.py` |
| `spark` | planned | (none yet) | - |
| `dataflow` | planned | (none yet) | - |

Both implemented adapters render the **same** engine-neutral SQL bodies
(`{{ ref('x') }}`, `{{ var('x') }}`) and the same generated patterns (staging dedupe and
quarantine, Type 2 dimensions, transaction facts, date dimension), so switching a layer's
engine changes syntax, not behaviour. The golden fixtures under `tests/golden/` pin both.
