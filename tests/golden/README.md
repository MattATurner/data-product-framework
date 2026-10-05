# Golden copies

A golden copy is the reviewed output of `dpf generate` for one product and engine:

| Directory | Product | Engine |
|---|---|---|
| `customer_orders/` | `customer_orders` | Dataform (declared) |
| `sales_performance/` | `sales_performance` | Dataform (declared) |
| `sales_performance--dbt/` | `sales_performance` | dbt (alternative adapter, kept reproducible) |

G3 runs `dpf generate --check`, which builds the product **twice** in memory and fails if
the two builds differ (nondeterminism: a timestamp, an unordered set) or if either differs
from the golden copy (drift). `dpf generate --all --check` also checks every alternative
engine that has a `<product>--<engine>/` directory here.

CI compiles the golden copies with the real tools: `terraform fmt -check` and `validate`,
Dataform `compile`, and `dbt parse`.

## Updating after an intended change

A change to a manifest, an authored SQL body, a methodology pack, the registry or a
generator changes the output. Regenerate, then **review the diff like code**:

```bash
make golden          # dpf generate --all --update-golden (every product and every engine with a copy)
git diff tests/golden/
```

To start keeping another engine reproducible, create its copy once:
`dpf generate <product> --engine dbt --update-golden`.

The build digest in each `MANIFEST.json` changes with any input, so evidence recorded for
the previous build becomes stale and G4 needs new evidence. That is intended: evidence
proves *this* build, not an earlier one.

Do not edit files here by hand. They are outputs, and `dpf lint` and `dpf validate` skip
them.
