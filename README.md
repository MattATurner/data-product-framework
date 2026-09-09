# Data Product Framework (DPF)

A spec-driven, skill-composable framework for specifying, designing, building and
governing **data products** on Google Cloud.

```
BRD spec  ──G0──▶  TDD spec  ──G1──▶  Build  ──G2/G3──▶  Publish + Catalog  ──G4──▶  Published
(business)         (engineering)      (agent)            (joint)                     (accepted)
```

The **data product is the atomic unit**. Every BRD scopes one, every TDD resolves one,
every pipeline exists to serve one.

## The five planes

| Plane | What it decides | Where |
|---|---|---|
| **Specs** | What the business needs (BRD) and how it will be met (TDD) | `openspec/specs/` |
| **Methodology** | What *shape* the data takes — optional and pluggable | `methodologies/` |
| **Engine & storage** | What *executes* the transform, and where data lands | `engines/`, per-layer config |
| **Skills** | Composable units of work across Extract / Load / Transform / Publish / Govern | `skills/` |
| **Contracts** | Typed handoffs that make skills composable | `contracts/` |

## Core rules

1. **The BRD contains no modelling vocabulary.** It is written by a business SME.
   Grain, SCD type and conformance are *derived* in the TDD and confirmed via a signed
   `semantics.md`.
2. **A methodology is a cost paid for a benefit.** `direct` (typed staging + business
   view) is the default. Kimball and Data Vault must be justified by a BRD signal.
3. **Prefer MCP servers and existing agents over bespoke code.** See
   `openspec/specs/platform/tool-selection/spec.md` and `registry/mcp_servers.yaml`.
4. **Nothing is built that cannot be traced to a business requirement**, and no design
   decision exists without a requirement ID.

## Template or example?

This repository is both a **template** and its own **reference implementation**. The seam
is mechanical, not a matter of discipline.

| | Paths | |
|---|---|---|
| **Template** | `openspec/specs/platform/` · `contracts/` · `methodologies/` · `engines/` · `skills/` · `registry/` · `tools/` · `tests/` | Reusable as-is |
| **Example** | `openspec/specs/products/` · `products/` · `examples/` · `docs/` | Deletable in one command |

**`registry/` ships empty by design.** A new project must not inherit someone else's bus
matrix, glossary, entities or source systems — that would make sample data a
specification, which is exactly what this framework forbids. The registry content the
worked examples need lives in `examples/registry/` as an overlay.

`registry/mcp_servers.yaml` is the exception and stays populated: the MCP and agent
catalogue is genuine platform infrastructure, not example data.

## Quickstart

### Starting a new project

```bash
tools/dpf init ../my-workspace     # template only, empty registry, no examples
```

Then set `gcp_project` and `region` in `registry/platform-defaults.yaml`, add your source
systems, and author a BRD with `skills/author-brd`.

### Running the worked examples in place

```bash
cp examples/registry/*.yaml registry/     # apply the example overlay first

tools/dpf validate                        # specs, contracts, skills, naming
tools/dpf lint                            # MCP / tool-tier enforcement
tools/dpf check customer_orders           # G0, G1, traceability, contract DAG
tools/dpf check sales_performance
make check                                # everything, including contract tests
```

## Worked examples

Two, deliberately at opposite ends of the methodology plane.

### 1. `customer_orders` — the `direct` path

A minimal product: object-store CSV ➜ raw ➜ typed staging ➜ business view with nested
order lines ➜ published and catalogued. Every gate exercised, no modelling ceremony.

`openspec/specs/products/sales/customer_orders/`

### 2. `sales_performance` — the Kimball path, with real artefacts

A full reference implementation against an on-premises Oracle source. The BRD's own
signals — reconciliation with Finance and Merchandising, plus point-in-time attribution —
are what *derive* Kimball; it is not asserted. Silver is Kimball, gold is `direct`,
demonstrating per-layer methodology selection.

Includes Dataform SQLX (SCD2 dimensions, transaction fact, generated grain assertions),
a watermark extract that runs beside the database, Terraform, two-phase seed fixtures and
a runbook.

`openspec/specs/products/sales/sales_performance/` and `examples/sales_performance/`

It also shows the framework catching a real constraint: the source cannot be reached
inbound from Google Cloud, so the 15-minute freshness requirement was **raised back to
the business** rather than quietly downgraded. They accepted hourly, and the BRD moved to
1.1.0 with the reason recorded.

## Layout

```
openspec/     project context, platform capability specs, product BRD+TDD specs, changes
contracts/    8 versioned JSON Schemas — the typed handoffs between skills
methodologies/ pluggable modelling packs (direct, kimball, ...)
engines/      transform engine adapters (dataform, dbt, dataflow, spark)
skills/       composable units of work
registry/     configuration: platform defaults, MCP servers, sources, conformance, glossary
products/     resolved manifests
generated/    disposable build output
tests/        contract tests, golden fixtures, agent evals
tools/dpf     the CLI
```
