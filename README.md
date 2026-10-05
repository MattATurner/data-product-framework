# Data Product Framework (DPF)

A spec-driven, composable data engineering toolkit for building **data products** on
Google Cloud. Specs live in [OpenSpec](https://openspec.dev); a small Python CLI, `dpf`,
checks a machine gate at every stage and generates everything that can be generated.

```
 DEFINE          DESIGN                 BUILD                     TEST              MONITOR
 BRD spec ─G0─▶  TDD + semantics ─G1─▶  compose ─G2─▶ generate ─G3─▶ evidence ─G4─▶  observe ─▶ breach ─▶ change
 (business)      + sign-off (joint)     (skills)      (artefacts)    (deployed run)  (policy)
```

The **data product is the atomic unit**. Every BRD scopes one, every TDD resolves one,
every artefact traces back to one of its requirements.

## What each gate proves

| Gate | Passes when | Command |
|---|---|---|
| **G0** Define | The BRD answers the rubric, is approved, and uses no modelling vocabulary | `dpf brd validate <product>` |
| **G1** Design | The TDD and manifest resolve every requirement; methodology, grain and history are justified; the business sign-off matches the semantic digest | `dpf check <product> --gate G1` |
| **G2** Compose | Each stage selects a skill and an implemented engine adapter; every business scenario (AX) maps to an acceptance test (AT) | `dpf check <product> --gate G2` |
| **G3** Build | Artefacts generate deterministically, match the reviewed golden copy, and every requirement reaches a decision, an artefact and a test | `dpf check <product> --gate G3` |
| **G4** Test | Every test has passing evidence for the **current** build digest | `dpf check <product> --gate G4` |
| Monitor | The deployed product meets its observability policy; a breach opens an OpenSpec change | `dpf monitor <product>` |

Gates are cumulative (`--gate G3` runs G0–G3). Exit code 0 means pass, 1 fail, 2 usage error,
and `--json` gives a machine-readable report, so the same commands run locally and in CI.

## Quick start

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'                     # gives you `dpf`; add [gcp] for live tests and monitoring
                                            # or `make install`: the hash-locked versions CI uses

dpf check --all --gate G3                   # both worked examples, G0 to G3: all pass
dpf generate sales_performance              # writes generated/sales_performance/
dpf trace sales_performance --print         # requirement -> decision -> element -> artefact -> test -> evidence
dpf test plan sales_performance             # every test case and what it satisfies
dpf check sales_performance --gate G4       # fails: no deployed-run evidence exists (by design)
dpf monitor sales_performance --evidence tests/evals/monitor-breach/run-evidence.json
dpf eval                                    # 19 behavioural evals
make ci                                     # what CI runs
```

Starting a new project: `dpf init ../my-workspace` copies the framework with an empty
registry and no example material.

## How it fits together

| Plane | Decides | Where |
|---|---|---|
| **Specs** | What the business needs (BRD) and how it is met (TDD, `semantics.md`, sign-off) | `openspec/specs/` |
| **Manifest** | The resolved design: sources, models, grain, history, quality, ports, schedules, governance, observability | `products/<id>/product.yaml` |
| **Methodology** | What *shape* the data takes. Optional and pluggable: `direct` (default) or `kimball` | `methodologies/` |
| **Engine adapters** | What runs the transforms: Dataform and dbt implemented; Dataflow and Spark planned | `engines/` |
| **Skills** | Composable units of work, selected per stage by `selects_when` | `skills/`, `methodologies/*/skills/` |
| **Contracts** | 22 JSON Schemas for every handoff, from BRD to run evidence | `contracts/` |
| **Generators** | Manifest + SQL bodies → Dataform or dbt, Terraform, tests, docs | `dpf/generate/` |

What one manifest generates, per product: the engine project (staging with quarantine
and reject views, Type 1/2 dimensions, facts, gold views, grain / history / reject-gate /
acceptance assertions), Terraform (datasets, access, policy tags and masking, BigQuery
sharing, orchestration, freshness and volume checks, alerts, Knowledge Catalog quality
scans, control tables), contract documents, `test-spec.json` and a `MANIFEST.json` whose
build digest binds test evidence to exactly this build.

## Core rules

1. **The BRD contains no modelling vocabulary.** A business SME writes it. Grain, history
   and conformance are *derived* in the TDD and played back in `semantics.md`, which the
   business signs. The signature is bound to a digest, so editing the semantics voids it.
2. **A methodology is a cost paid for a benefit.** `direct` is the default. Departing from
   it needs an ADR, and G1 compares the choice with what the BRD signals recommend:
   figures that must agree with another team, or past figures that keep the values that
   applied at the time.
3. **Prefer MCP servers and existing agents over bespoke code.** Every skill declares a
   tool tier; `dpf lint` fails tier 4–5 work that a tier 1–3 server covers, and bespoke
   code must cite an ADR.
4. **Nothing is built that cannot be traced to a requirement**, and nothing is accepted
   without evidence for the build being accepted.
5. **Generated artefacts are never edited by hand.** Change the inputs, regenerate, and
   review the golden diff.

## Template or example?

| | Paths |
|---|---|
| **Template** (copied by `dpf init`) | `openspec/` config, schema, project context and `specs/platform/`; `contracts/`, `methodologies/`, `engines/`, `skills/`, `registry/`, `adr/`, `dpf/`, CI, `docs/user-guide.md`, eval and golden READMEs |
| **Example** (not copied) | `openspec/specs/products/`, `products/`, `examples/`, `tests/golden/*`, `evidence/`, the plan, method diagram and presentation in `docs/` |

**`registry/` ships empty by design**, so a new project never inherits someone else's
glossary, entities or source systems. The examples declare `registry_overlay:
examples/registry` in their manifests and read that overlay without changing `registry/`.
`registry/mcp_servers.yaml` stays populated: the MCP catalogue is platform infrastructure.

## Worked examples

| | `customer_orders` | `sales_performance` |
|---|---|---|
| Path | `direct` | Kimball silver, `direct` gold |
| Source | object-store CSV | on-premises Oracle, outbound watermark extract (ADR-015) |
| BRD | BRD-SALES-001 @ 1.1.0 | BRD-SALES-002 @ 1.2.0 |
| Shows | the minimum: every gate, no modelling ceremony | Type 2 history, quarantine + reject gate (R-11), masking (R-12), partner sharing (R-13), monitoring |

`sales_performance` also shows the framework catching a real constraint: the source cannot
be reached inbound from Google Cloud, so the 15-minute freshness requirement was **raised
back to the business** rather than quietly downgraded. They accepted hourly, and the BRD
moved to 1.1.0 with the reason recorded. See `examples/sales_performance/RUNBOOK.md`.

**Status of the examples:** G0–G3 pass. G4 fails because nobody has deployed them and
recorded evidence, which is the honest state. The sign-offs in `tdd/signoff.yaml` are
example signatures ("Sales Operations (example)"), not real approvals.

## Verified with the real tools

The golden copies are checked in CI (`.github/workflows/ci.yml`) and were verified locally:
`terraform fmt -check` and `terraform validate` (both products, and the example wrapper),
Dataform `compile` (both products, 0 errors) and `dbt parse` (the dbt rendering of
`sales_performance`).

## Documentation

| | |
|---|---|
| **User guide** | [`docs/user-guide.md`](docs/user-guide.md) |
| **Presentation** | [`docs/presentation/index.html`](docs/presentation/index.html) (open from disk) |
| Method diagram (interactive, offline) | [`docs/index.html`](docs/index.html), generated from the plan by `cd docs && python3 build_method_diagram.py` |
| Design narrative | [`docs/data-product-framework-plan.md`](docs/data-product-framework-plan.md) |
| Connecting an on-premises source | [`docs/local-source-connectivity.md`](docs/local-source-connectivity.md) |
| Agent rules | [`openspec/AGENTS.md`](openspec/AGENTS.md) |
| Decisions | [`adr/`](adr/README.md) |

## Layout

```
openspec/        project context, custom `data-product` schema, platform + product specs, changes
contracts/       22 versioned JSON Schemas: the typed handoffs
dpf/             the CLI: gates, compose, generate/, trace, testing, monitor, lint, evals
methodologies/   modelling packs (direct, kimball): roles, rules, skills
engines/         engine adapters (dataform, dbt implemented; dataflow, spark planned)
skills/          platform skills (Agent Skills format with dpf metadata)
registry/        platform defaults, MCP servers, BRD rubric and vocabulary (no example data)
adr/             architecture decision records
products/        resolved manifests, SQL bodies, acceptance mappings
examples/        registry overlay, extractor, seed fixtures, Terraform wrapper, runbook
generated/       build output (gitignored; regenerate at will)
evidence/        test evidence per product and build digest (created by dpf test)
tests/           unit, contract, golden copies, behavioural evals
```
