# Example registry overlay

`registry/` in the template ships **empty by design** — a new project must not inherit a
bus matrix full of someone else's dimensions, or a glossary defining someone else's
measures.

These files are the registry content the two worked examples need. To run the examples
as-is:

```bash
cp examples/registry/*.yaml registry/
```

| File | Provides |
|---|---|
| `source_systems.yaml` | `example_files` (object drop) and `ora_local` (on-prem Oracle) |
| `entities.yaml` | order, order line, customer |
| `conformance.yaml` | `dim_customer`, `dim_product`, `dim_date` owned by the sales domain |
| `glossary.yaml` | `net_amount`, `order_status` |

`registry/mcp_servers.yaml` is **not** overlaid — the MCP server catalogue is genuinely
reusable platform infrastructure, not example data, so it stays in the template.
