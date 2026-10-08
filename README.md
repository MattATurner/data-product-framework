# Data Product Framework (DPF)

A spec-driven, composable data engineering toolkit for building **data products** on
Google Cloud. Specs live in [OpenSpec](https://openspec.dev); a small Python CLI, `dpf`,
checks a machine gate at every stage and generates everything that can be generated.

![The data product cycle. Define (use case, score and choose, BRD or PRD) passes gate G0 to Design (TDD and manifest, semantics.md, business sign-off), G1 to Compose (skill per stage, engine adapter, scenario to test), G2 to Build (generate, golden copy), G3 to Test (deploy and run, evidence) and G4 to Monitor (observe, breach). A breach or a new need opens an OpenSpec change, which passes the same gates again.](docs/images/dpf-lifecycle.svg)

Define starts before the BRD: the business describes each candidate use case, scores it for
value and ease, and chooses what to build, with the [templates](templates/README.md). After
the first release, every change goes round the same gates, so each loop leaves new evidence.

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
dpf check sales_performance --gate G4       # 41 of 43 pass (sandbox evidence); AT-5 and AT-8 await attestation
dpf monitor sales_performance --evidence tests/evals/monitor-breach/run-evidence.json
dpf eval                                    # 19 behavioural evals
make ci                                     # what CI runs
```

Starting a new project: `dpf init ../my-workspace` copies the framework and the Define and
Design templates, with an empty registry and no example material.

## How it fits together

| Plane | Decides | Where |
|---|---|---|
| **Specs** | What the business needs (BRD) and how it is met (TDD, `semantics.md`, sign-off) | `openspec/specs/` |
| **Templates** | Which use cases go ahead (scored and chosen before any BRD), and the starting shape of each Define and Design document | `templates/` |
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
| **Template** (copied by `dpf init`) | `openspec/` config, schema, project context, agent rules, changes README and `specs/platform/`; `contracts/`, `methodologies/`, `engines/`, `skills/`, `registry/`, `adr/`, `dpf/`, `tools/dpf`, `requirements/`, `pyproject.toml`, `Makefile`, `.gitignore`, CI, contract tests, `docs/user-guide.md`, `templates/`, eval and golden READMEs |
| **Example** (not copied) | `openspec/specs/products/`, `products/`, `examples/`, `tests/golden/*`, `evidence/`, the plan, method diagram, presentation and README diagram in `docs/` |

**`registry/` ships without project content by design**: the source-system, glossary,
entity and conformance catalogues are empty, so a new project never inherits someone
else's. The examples declare `registry_overlay: examples/registry` in their manifests and
read that overlay without changing `registry/`. Framework configuration ships populated:
`platform-defaults.yaml` (set your project, region and business time zone), the BRD rubric
and vocabulary (`brd-rubric.yaml`, `brd-vocabulary.yaml`) and the MCP catalogue
(`mcp_servers.yaml`).

## Worked examples

| | `customer_orders` | `sales_performance` |
|---|---|---|
| Path | `direct` | Kimball silver, `direct` gold |
| Source | object-store CSV | on-premises Oracle, outbound watermark extract (ADR-015) |
| Define | none | UC-SALES-001: use case, scorecard (a quick win), prioritisation and BRD as filled PDFs |
| BRD | BRD-SALES-001 @ 1.1.0 | BRD-SALES-002 @ 1.2.0 |
| Shows | the minimum: every gate, no modelling ceremony | Type 2 history, quarantine + reject gate (R-11), masking (R-12), partner sharing (R-13), monitoring |

UC-SALES-001 ([`examples/sales_performance/define/`](examples/sales_performance/define/README.md))
was written after the product to show the chain from use case to design, so its scores are
illustrative. [`examples/use-case-portfolio/`](examples/use-case-portfolio/README.md) scores
the three use cases of the seed template on the same scorecard.

`sales_performance` also shows the framework catching a real constraint: the source cannot
be reached inbound from Google Cloud, so the 15-minute freshness requirement was **raised
back to the business** rather than quietly downgraded. They accepted hourly, and the BRD
moved to 1.1.0 with the reason recorded. See `examples/sales_performance/RUNBOOK.md`.

**Status of the examples:** G0–G3 pass for both. `sales_performance` was deployed to a
sandbox project on 5 October 2026: 41 of its 43 test cases pass for build
`sha256:fd95e365e03e…` (evidence in `evidence/sales_performance/`). G4 still fails on AT-5
and AT-8, which need a person from Finance and from Merchandising to attest. `customer_orders`
has not been deployed, so G4 fails with 14 missing results. The sign-offs in
`tdd/signoff.yaml` are example signatures ("Sales Operations (example)"), not real approvals.

## Verified with the real tools

The golden copies and the example Terraform wrapper are checked in CI
(`.github/workflows/ci.yml`, pinned tool versions) and were verified locally with the same
versions: Terraform 1.9.8 `fmt -check` and `validate` (all three golden modules and the
wrapper), Dataform CLI 3.0.71 `compile` (both products, 0 errors) and dbt 1.12.5 `parse` (the
dbt rendering of `sales_performance`: 18 models, 36 tests, 4 sources).

The sandbox deployment of `sales_performance` applied all 37 Terraform resources, built all
54 Dataform actions, and passed every SQL acceptance case. It also found four problems that
offline checks cannot see, now fixed; see section 15 of the [user guide](docs/user-guide.md).

## Documentation

| | |
|---|---|
| **User guide** | [`docs/user-guide.md`](docs/user-guide.md) |
| **Define and Design templates** | [`templates/README.md`](templates/README.md): use case, scorecard, prioritisation, BRD or PRD (fillable PDFs); TDD, semantics, manifest and ADR (Markdown and YAML) |
| **Define worked examples** (filled PDFs) | UC-SALES-001: [use case](examples/sales_performance/define/use-case.pdf), [scorecard](examples/sales_performance/define/scorecard.pdf), [prioritisation](examples/sales_performance/define/prioritisation.pdf), [BRD](examples/sales_performance/define/brd.pdf). The seed's three use cases: [scorecard](examples/use-case-portfolio/scorecard.pdf), [prioritisation](examples/use-case-portfolio/prioritisation.pdf) |
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
tools/dpf        runs the CLI from a checkout without installing it
methodologies/   modelling packs (direct, kimball): roles, rules, skills
engines/         engine adapters (dataform, dbt implemented; dataflow, spark planned)
skills/          platform skills (Agent Skills format with dpf metadata)
registry/        platform defaults, MCP servers, BRD rubric and vocabulary (no example data)
adr/             architecture decision records
templates/       Define-stage forms (fillable PDFs) and Design-stage templates (Markdown, YAML)
docs/            user guide, presentation, design narrative, method diagram, README diagram (images/)
products/        resolved manifests, SQL bodies, acceptance mappings
examples/        registry overlay, extractor, seed fixtures, Terraform wrapper, runbook, Define examples
generated/       build output (gitignored; regenerate at will)
evidence/        test evidence per product and build digest (created by dpf test)
tests/           unit, contract, golden copies, behavioural evals
requirements/    hash-locked Python requirements: dev, dbt, templates
```
