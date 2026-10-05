# Example registry overlay

`registry/` in the template ships **empty by design**. A new project must not inherit a
bus matrix full of someone else's dimensions, or a glossary defining someone else's
measures.

These files are the registry content the two worked examples need. You do **not** copy
them. Each example product names this folder in its manifest:

```yaml
# products/sales_performance/product.yaml
registry_overlay: examples/registry
```

`dpf` merges the overlay over `registry/` **on read**, matching entries by their identity
key (`system_id`, `name` or `id`). Nothing is written to `registry/`, so the template stays
clean and `dpf init` never copies example data.

| File | Provides |
|---|---|
| `source_systems.yaml` | `example_files` (object drop) and `ora_local` (on-premises Oracle), with supported capture modes |
| `entities.yaml` | order, order line, customer, product |
| `conformance.yaml` | `dim_customer`, `dim_product`, `dim_date` owned by the sales domain |
| `glossary.yaml` | every figure and attribute named in the two BRDs |

`registry/mcp_servers.yaml`, `registry/brd-rubric.yaml` and `registry/brd-vocabulary.yaml`
are **not** overlaid. They are reusable platform data, not example data.
