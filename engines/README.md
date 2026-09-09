# Engine adapters

Methodology packs emit `semantic-model.v1`. Engine adapters render that model into
executable artefacts. **Packs never emit engine-specific artefacts, and adapters never
make modelling decisions.** If either side starts knowing about the other, the plane
has leaked.

| Engine | Status | Renders to |
|---|---|---|
| `dataform` | default | SQLX models, assertions, workflow configs |
| `dbt` | supported | models, tests, sources |
| `dataflow` | supported for streaming-capable roles | Beam pipeline |
| `spark` | escape hatch | Managed Service for Apache Spark job |

Support is declared **per methodology role** in each pack's `methodology.yaml`, not
globally. `dpf compose` fails an unsupported pairing at G1.
