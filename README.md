# Data Product Framework (DPF)

A spec-driven, composable data engineering toolkit for building **data products** on
Google Cloud. Specs live in [OpenSpec](https://openspec.dev); a small Python CLI, `dpf`,
checks a machine gate at every stage and generates everything that can be generated.

![The data product cycle — 6 human-gated steps. 1. Discover & Prioritise (use case, readiness QA, score and choose) moves to 2. Describe (BRD or PRD rubric, rubric check, approve need), passes gate G0 to 3. Design (TDD and manifest, semantics.md playback, sign digest), G1 to 4. Build (compose skills at G2, multi-plane generate, golden copy PR), G3 to 5. Accept (deploy and run live, build digest proof, domain attest) and G4 to 6. Monitor (published product, working-hours watch, change loop). A breach or a new need opens an OpenSpec change, which passes the same gates again.](docs/images/dpf-lifecycle.svg)

The cycle runs across **six human-gated steps**. **Discover & Prioritise** starts before the
BRD: the business describes each candidate use case, scores it for value and ease, and
chooses what to build, with the [templates](framework/templates/README.md). The `assess-use-case`
agent skill checks each filled use case against its template before the panel scores it.
**Describe** captures the funded need in plain business English, **Design** grounds it in
organisational context and locks business playback sign-off to a semantic digest, **Build**
composes skills and generates every cloud plane into a reviewed golden copy, **Accept**
proves live outcomes and domain attestations per build digest, and **Monitor** watches
working-hours SLAs so every subsequent change goes round the same gates and leaves new
evidence.

The **data product is the atomic unit**. Every BRD scopes one, every TDD resolves one,
every artefact traces back to one of its requirements.

## What each gate proves

| Step | Gate | Passes when | Command |
|---|---|---|---|
| **1. Discover & Prioritise** | Portfolio | Candidate use case is complete (`assess-use-case`) and scored for value and ease | [templates](framework/templates/README.md) |
| **2. Describe** | **G0** | The BRD answers the rubric, is approved, and uses no modelling vocabulary | `dpf brd validate <product>` (or `--gate describe`) |
| **3. Design** | **G1** | The TDD and manifest resolve every active requirement; methodology, grain and history are justified; the business sign-off matches the semantic digest | `dpf check <product> --gate G1` (or `--gate design`) |
| **4. Build** *(Compose)* | **G2** | Each stage selects a skill and an implemented engine adapter; every business scenario (AX) maps to an acceptance test (AT) | `dpf check <product> --gate G2` (or `--gate compose`) |
| **4. Build** *(Generate)* | **G3** | Artefacts generate deterministically, match the reviewed golden copy, and every requirement reaches a decision, an artefact and a test | `dpf check <product> --gate G3` (or `--gate build`) |
| **5. Accept** | **G4** | Every test and human attestation has passing evidence for the **current** build digest | `dpf check <product> --gate G4` (or `--gate accept`) |
| **6. Monitor** | Day 2 | The deployed product meets its observability policy; a breach opens an OpenSpec change | `dpf monitor <product>` |

Gates are cumulative (`--gate G3` or `--gate build` runs G0–G3), and accept either the number (`G0`–`G4`) or the stage name (`describe`/`define`, `design`, `compose`, `build`, `accept`/`test`). Exit code 0 means pass, 1 fail, 2 usage error, and `--json` gives a machine-readable report, so the same commands run locally and in CI.

**What is a golden copy?** A [golden copy](tests/golden/README.md) (`tests/golden/<product>/`) is the committed, human-reviewed snapshot of `dpf generate` output. At G3, `dpf` builds the product twice in memory to prove generation is deterministic, then compares the output against `tests/golden/<product>/` so any unintended change to generated SQL, Terraform or tests is caught in pull-request review.

**What is a Goldfish check?** Deterministic gates (`dpf check`) prove schema conformance, vocabulary rules, traceability and byte-identical generation, but they cannot catch semantic blind spots when the *same* long-lived coding-agent session interviews the business, resolves the TDD, writes `semantics.md` (`playback.md`) and authors custom SQL. Borrowing from Google's [Elephant-Goldfish Model](https://github.com/google/elephant-goldfish-model), DPF pairs **the Elephant** (your context-rich session that remembers every requirement and trade-off) with **Goldfish checks** ([`.agents/skills/goldfish-verify`](.agents/skills/goldfish-verify/SKILL.md))—fresh, zero-context subagents handed *only* the artefacts under test and none of the conversation:

- **G0 · Describe** — reads `checks.json` or the draft BRD cold to flag vague measures and disguised design choices that slipped past the static word list.
- **G1 · Design** — reads *only* `product.yaml` and `products/<id>/sql/*.sql` (never the BRD or `semantics.md`) to reconstruct a blind business-language playback (`generated/<id>/goldfish-playback.md`), surfacing silent design drift before `dpf signoff`.
- **G3 · Build** — audits custom SQL and acceptance queries cold for offline traps (`HAVING` alias collisions, grain-multiplying joins, vacuous zero-row assertions) that `compile` and `parse` cannot see before updating `tests/golden/`.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install '.[dev]'                        # installs `dpf` (use `pip install -e '.[dev]'` if editing dpf itself;
                                            # add [gcp] for live tests/monitoring, or `make install` for CI hash pins)

dpf check --all --gate G3                   # both worked examples, G0 to G3: all pass (also accepts `--gate build`)
dpf generate sales_performance              # writes generated/sales_performance/
dpf trace sales_performance --print         # requirement -> decision -> element -> artefact -> test -> evidence
dpf test plan sales_performance             # every test case and what it satisfies
dpf check sales_performance --gate G4       # 41 of 43 pass (sandbox evidence); AT-5 and AT-8 await attestation
dpf monitor sales_performance --evidence tests/evals/monitor-breach/run-evidence.json
dpf eval                                    # 26 behavioural evals
make ci                                     # what CI runs
```

Starting a new project: `dpf init ../my-workspace` copies the framework and the Define and
Design templates, with an empty registry and no example material.

## How it fits together

| Plane | Decides | Where |
|---|---|---|
| **Specs** | What the business needs (BRD) and how it is met (TDD, `semantics.md`, sign-off) | `openspec/specs/` |
| **Templates** | Which use cases go ahead (scored and chosen before any BRD), and the starting shape of each Define and Design document | `framework/templates/` |
| **Manifest** | The resolved design: sources, models, grain, history, quality, ports, schedules, governance, observability | `products/<id>/product.yaml` |
| **Methodology** | What *shape* the data takes. Optional and pluggable: [`direct`](framework/methodologies/direct/METHODOLOGY.md) (default: stage, type and expose business views/tables directly with declared grain—no star-schema ceremony) or [`kimball`](framework/methodologies/kimball/METHODOLOGY.md) (conformed dimensions and facts) | `framework/methodologies/` |
| **Engine adapters** | What runs the transforms: Dataform and dbt implemented; Dataflow and Spark planned | `framework/engines/` |
| **Skills** | Composable units of work, selected per stage by `selects_when` | `framework/skills/`, `framework/methodologies/*/skills/` |
| **Agent skills** | Which skills a coding agent loads: the 11 it runs itself, not the 15 pipeline steps that `dpf compose` and `dpf generate` handle. Also agent-only skills, such as `assess-use-case` (checks a use case before the panel scores it) and `goldfish-verify` (runs zero-context subagent semantic checks at G0, G1 and G3) | `.agents/` |
| **Contracts** | 24 JSON Schemas for every handoff, from BRD to foundation bindings, semantic layers and run evidence | `framework/contracts/` |
| **Generators** | Manifest + SQL bodies → Dataform or dbt, LookML views/explores/dashboards, Terraform, tests, docs | `dpf/generate/` |

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
   review the golden diff. When source data is messy, write custom SQL cleansing, casting
   and joins in `products/<id>/sql/*.sql`; `dpf` wraps your SQL with deduplication,
   quarantine routing and assertions.

## Common design questions

- **Why `product.yaml` instead of writing dbt or Dataform directly?** One rule in
  `product.yaml` (such as a quarantine rule `QR-1` or policy tag `PT-1`) coordinates
  multiple planes at once: it generates the staging `_valid` and `_rejects` views and
  blocking assertion in Dataform or dbt, the datasets, IAM grants, policy tags and
  Knowledge Catalog quality scans in Terraform, the G4 test case, and the requirement trace
  matrix. Meanwhile, messy source cleansing stays in plain SQL (`products/<id>/sql/*.sql`),
  so you never lose SQL control.
- **How does DPF relate to existing observability (Slack, PagerDuty) and engine tests?**
  DPF generates Cloud Monitoring alert policies wired to your existing Slack or PagerDuty
  notification channel (`var.alert_channel`) and compiles automated acceptance SQL into
  native Dataform assertions or dbt tests. What DPF adds is **business-calendar evaluation**
  (for example, checking freshness only during Perth working hours), **attestations** for
  checks SQL cannot prove, and **requirement traceability** so a breach can open a pre-filled
  OpenSpec change (`dpf monitor --open-change`) naming the exact BRD requirement at risk.
- **Where does DPF use OpenSpec as-is, and where does it extend it?** DPF uses OpenSpec's
  directory structure (`openspec/specs/`, `openspec/changes/`), `Requirement`/`Scenario`
  markdown grammar, delta specs (`ADDED`/`MODIFIED`/`REMOVED`), `openspec validate --strict`,
  and custom workflow schemas (`openspec/schemas/data-product/schema.yaml`). DPF extends
  OpenSpec by splitting each product into a business-language BRD (`brd/spec.md` + `brd.yaml`)
  and a technical TDD (`tdd/spec.md` + `semantics.md` + `signoff.yaml`), adding traceable
  metadata lines (`**ID:** R-1`, `**Status:** deferred`, `**Decision:** D-3`), and enforcing
  machine gates G0–G4.
- **How does DPF integrate with Dataform's native Data Engineering Agent?** DPF keeps
  control-plane semantics, cross-plane orchestration and gate enforcement outside the engine,
  treating Dataform's native agent as a bounded Tier 3 leaf worker ([ADR-017](docs/adr/ADR-017-engine-native-agents.md))
  for messy source SQL wrangling, runtime failure diagnosis and rapid prototyping
  (`dpf proto import-dataform <product> --from <dir>`). Every Dataform build emits a
  deterministic `dataform/GEMINI.md` guardrail file, attaches BigQuery table labels for
  Knowledge Catalog discovery, and disables hourly auto-release schedules on governed
  products so unreviewed console edits cannot silently reach production.
- **How does DPF govern Looker Explores and Dashboards — including when a Looker request
  arrives after the BigQuery foundation already exists?** LookML views, surrogate-key
  Explores, aggregate-awareness tables and Stephen Few `.dashboard.lookml` dashboards are
  first-class governed artefacts ([ADR-018](docs/adr/ADR-018-looker-semantic-and-presentation-plane.md)).
  Products can be **coupled** (generating Dataform/dbt + LookML in one lifecycle, like
  `sales_performance`) or **decoupled** (`upstream:` binding an existing DPF product or a
  pre-existing BigQuery dataset from `registry/foundations.yaml` with zero `sources` or
  `staging` ceremony, plus optional thin `gold` views). G1 blocks Looker PDTs unless backed
  by an ADR, enforces surrogate-key joins on SCD2 dimensions, checks field resolution across
  Explores and tiles, and enforces zero-baseline bars; `dpf proto import-looker <product> --from <dir>`
  imports existing LookML projects into prototype mode.
- **How does DPF ensure enterprise governance (PII, data contracts, purpose-based access,
  retention) without reinventing a governance platform?** DPF acts as the deterministic
  build-time factory and integrates symbiotically with the Agentic Data Governance Framework
  (`AGF` / `ADG-00`, [ADR-019](docs/adr/ADR-019-symbiotic-agentic-governance-framework.md)) using
  Knowledge Catalog as the shared contract bus. When `governance.agf.enabled: true` is set in
  `product.yaml`, G1 enforces compile-time policy-tag coverage on `RESTRICTED` columns
  (imported from `ADG-01` Sensitive Data Protection scans or restricted glossary terms),
  blocks `RESTRICTED` columns from external BigQuery sharing ports, validates sovereign
  deployment regions, and emits all seven canonical `ADG-00` Single-Writer Aspect payloads in
  `catalog-registration.json` for continuous run-time enforcement across `ADG-01`–`ADG-05`.

## Template or example?

| | Paths |
|---|---|
| **Template** (copied by `dpf init`) | `openspec/` config, schema, project context, agent rules, changes README and `specs/platform/`; `.agents/` (skill wiring, `assess-use-case`, `goldfish-verify`); `framework/` (`contracts/`, `methodologies/`, `engines/`, `skills/`, `templates/`); `registry/`, `docs/adr/`, `docs/user-guide.md`, `dpf/`, `pyproject.toml`, `Makefile`, `.gitignore`, `.github/` (CI + hash-locked requirements), contract tests, eval and golden READMEs |
| **Example** (not copied) | `openspec/specs/products/`, `products/`, `examples/` (including sandbox `examples/evidence/`), `tests/golden/*`, `docs/fhd/`, and the plan, method diagram, presentation and README diagram in `docs/` |

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
| Source | object-store CSV | on-premises PostgreSQL 16 (`pg_local`), 15-min outbound watermark extract (ADR-015) |
| Define | none | UC-SALES-001: use case, scorecard (a quick win), prioritisation and BRD as filled PDFs |
| BRD | BRD-SALES-001 @ 1.1.0 | BRD-SALES-002 @ 1.2.0 |
| Shows | the minimum: every gate, no modelling ceremony | Type 2 history, quarantine + reject gate (R-11), masking (R-12), partner sharing (R-13), LookML Explore + dashboard (ADR-018), monitoring |

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
`sha256:fd95e365e03e…` (evidence in `examples/evidence/sales_performance/`). G4 still fails on AT-5
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
| **Define and Design templates** | [`framework/templates/README.md`](framework/templates/README.md): use case, scorecard, prioritisation, BRD or PRD (fillable PDFs); TDD, semantics, manifest and ADR (Markdown and YAML) |
| **Define worked examples** (filled PDFs) | UC-SALES-001: [use case](examples/sales_performance/define/use-case.pdf), [scorecard](examples/sales_performance/define/scorecard.pdf), [prioritisation](examples/sales_performance/define/prioritisation.pdf), [BRD](examples/sales_performance/define/brd.pdf). The seed's three use cases: [scorecard](examples/use-case-portfolio/scorecard.pdf), [prioritisation](examples/use-case-portfolio/prioritisation.pdf) |
| **Presentation** | [`docs/presentation/index.html`](docs/presentation/index.html) (open from disk) |
| Method diagram (interactive, offline) | [`docs/index.html`](docs/index.html), generated from the plan by `cd docs && python3 build_method_diagram.py` |
| Design narrative | [`docs/data-product-framework-plan.md`](docs/data-product-framework-plan.md) |
| Connecting an on-premises source | [`docs/local-source-connectivity.md`](docs/local-source-connectivity.md) |
| Agent rules | [`openspec/AGENTS.md`](openspec/AGENTS.md) |
| Functional Hierarchy (`DPF-00`) | [`docs/fhd/DPF_Functional_Hierarchy_Dictionary.md`](docs/fhd/DPF_Functional_Hierarchy_Dictionary.md), [`docs/fhd/dpf-data-product-framework-fhd.html`](docs/fhd/dpf-data-product-framework-fhd.html) (open from disk), or live [FHD Server (`?cap=DPF`)](https://fhd-server-ttw6mmyb7a-uc.a.run.app/fhd-server?cap=DPF) |
| Decisions | [`docs/adr/`](docs/adr/README.md) |

## Repository structure & `DPF-00` capability map

The root is organised into **eight visible directories** (plus `.agents/` and `.github/`), cleanly separating **how the framework runs** (`dpf/`, `framework/`), **what product teams author** (`openspec/`, `registry/`, `products/`), and **worked examples, documentation & verification** (`examples/`, `docs/`, `tests/`). [`docs/fhd/`](docs/fhd/DPF_Functional_Hierarchy_Dictionary.md) decomposes DPF left-to-right across the six human-gated steps (`DPF-01`–`DPF-06`) and maps every leaf capability (`?lens=impl`) directly to its repository entrypoint:

```
data-product-framework/
├── dpf/                     [DPF-02..06] Python CLI & multi-plane compiler (`dpf` / `python -m dpf`)
├── framework/               [All stages] Declarative framework packs & starter templates:
│   ├── contracts/                        24 Draft 2020-12 JSON Schemas for every stage & AGF handoff
│   ├── engines/                          execution adapters (`dataform`, `dbt`; `dataflow`, `spark` planned)
│   ├── methodologies/                    modelling packs (`direct` default, `kimball`), rules & pack skills
│   ├── skills/                           composable platform & pipeline stage skills (Agent Skills format)
│   └── templates/                        Define-stage fillable PDF scorecards & Design starter scaffolds
│
├── openspec/                [DPF-02..06] Specifications: platform specs, BRDs, TDDs & `changes/` (OpenSpec CLI)
├── registry/                [DPF-02..03] Organisational context: defaults, glossary, sources, foundations, MCP
├── products/                [DPF-03..04] Resolved product manifests (`product.yaml`), custom `sql/`, acceptance
│
├── examples/                [DPF-01..05] Worked overlay, PostgreSQL simulator & extractor, seeds & `evidence/`
├── docs/                    [Docs]       User guide, `adr/` (ADR-001..019), `fhd/` (DPF-00), deck & diagrams
├── tests/                   [DPF-04..06] Unit tests, contract checks, `golden/` snapshots & 26 `evals/`
│
├── .agents/                 [DPF-01..04] Coding-agent skill wiring (`skills.json`), `assess-use-case`, `goldfish-verify`
└── .github/                 [CI]         GitHub Actions workflows & hash-locked Python pins (`requirements/`)
```
*(Running `dpf generate` and `dpf test run` in a workspace creates gitignored `generated/` and `evidence/` on demand.)*
