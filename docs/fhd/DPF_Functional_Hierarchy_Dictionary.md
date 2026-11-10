# DPF-00 Functional Hierarchy Dictionary

Canonical 6-pillar functional decomposition (DPF-00) of the Data Product Framework, ordered left-to-right across the 6 human-gated steps and mapped directly to the repository paths that implement each capability.

Live interactive FHD viewer: [DPF-00 on FHD Server](https://fhd-server-ttw6mmyb7a-uc.a.run.app/fhd-server?cap=DPF) (toggle to the Implementation lens `?lens=impl` to inspect entrypoints and CLI commands).

| UID | Capability / Module | Node Type | Impl Mode | Repository Entrypoint | One-Line Responsibility |
| :--- | :--- | :---: | :---: | :--- | :--- |
| DPF-00 | Data Product Framework | capability | multi_stack | `dpf/cli.py · framework/skills/ · framework/contracts/ · framework/methodologies/ · framework/engines/` | Accelerates enterprise data products from candidate use case to governed outcome in 6 human-gated steps. |
| DPF-01 | 1. Discover & Prioritise | capability | multi_stack | `framework/templates/define/ · framework/templates/scoring.yaml · .agents/skills/assess-use-case/` | Evaluates candidate business ideas and ranks Value vs Ease before engineering starts. |
| DPF-01-01 | Use-Case Readiness Agent | agent | adk_agent | `.agents/skills/assess-use-case/SKILL.md` | Reviews candidate submissions against the 11-criterion evidence rubric before panel scoring. |
| DPF-01-02 | 11-Criterion Scoring Engine | business_function | cli_batch | `framework/templates/scoring.yaml` | Calculates weighted Value (3.05) and Ease (3.33) scores across eleven portfolio criteria. |
| DPF-01-03 | Portfolio Gate Workbench | ui_workbench | chat_ui | `framework/templates/define/` | Presents the 2x2 Quick Win vs Strategic Bet matrix for human funding sign-off. |
| DPF-02 | 2. Describe (Gate G0) | capability | multi_stack | `dpf/brd.py · framework/skills/author-brd/ · framework/skills/validate-brd/` | Captures structured plain-English business requirements and validates rubric completeness. |
| DPF-02-01 | Plain-English BRD Author | agent | adk_agent | `framework/skills/author-brd/SKILL.md` | Interviews business stakeholders and drafts requirements strictly in commercial language. |
| DPF-02-02 | Gate G0 Rubric Validator | business_function | cli_batch | `dpf/brd.py` | Verifies groups A-K completeness, glossary alignment, and zero technical jargon. |
| DPF-02-03 | Business Need Sign-Off | ui_workbench | chat_ui | `openspec/specs/products/sales/sales-performance/brd/spec.md` | Captures named business owner approval on the jargon-free requirement specification. |
| DPF-02-04 | Prototype Sandbox Importer | integration | cli_batch | `dpf/dataform_import.py · dpf/looker_import.py` | Imports existing Dataform or LookML repositories into fast-path prototype mode. |
| DPF-03 | 3. Design (Gate G1) | capability | multi_stack | `dpf/design.py · framework/methodologies/ · .agents/skills/goldfish-verify/` | Resolves grain, history, methodology, Looker safety, and AGF privacy rules with playback sign-off. |
| DPF-03-01 | TDD & Methodology Resolver | agent | adk_agent | `framework/skills/resolve-tdd/SKILL.md` | Recommends direct vs Kimball modelling and surfaces source connectivity constraints early. |
| DPF-03-02 | Gate G1 & AGF Privacy Engine | business_function | cli_batch | `dpf/design.py` | Enforces grain parity, SCD2 surrogate joins, Looker rules, and AGF C6/C10 privacy gates. |
| DPF-03-03 | Zero-Context Playback Critic | agent | adk_agent | `.agents/skills/goldfish-verify/SKILL.md` | Audits product.yaml and SQL blind against semantics.md to catch conversational anchoring. |
| DPF-03-04 | Playback Sign-Off Ledger | crud_module | cli_batch | `openspec/specs/products/sales/sales-performance/tdd/signoff.yaml` | Persists SHA-256 semantic digest signatures in signoff.yaml to lock business meaning. |
| DPF-03-05 | Business Playback Gate | ui_workbench | chat_ui | `openspec/specs/products/sales/sales-performance/tdd/semantics.md` | Presents one-page plain-English semantics.md for business owner confirmation. |
| DPF-04 | 4. Build (Gates G2-G3) | capability | multi_stack | `dpf/compose.py · dpf/generate/` | Composes stage skills and compiles deterministic SQL, Terraform, Catalog, and LookML. |
| DPF-04-01 | Gate G2 Pipeline Composer | business_function | cli_batch | `dpf/compose.py` | Selects stage skills and type-checks contract handoffs and engine support across the DAG. |
| DPF-04-02 | Bounded Dataform SQL Agent | agent | adk_agent | `dpf/generate/dataform.py` | Assists messy source SQL wrangling inside deterministic GEMINI.md guardrails. |
| DPF-04-03 | Gate G3 Multi-Plane Compiler | business_function | cli_batch | `dpf/generate/__init__.py` | Compiles Dataform/dbt SQL, Terraform IAM, LookML, and 7 ADG-00 Catalog aspects. |
| DPF-04-04 | Watermark Control Ledger | crud_module | terraform_iac | `dpf/generate/terraform.py` | Maintains atomic high-watermark and batch manifest rows in dpf_watermark_log. |
| DPF-04-05 | Golden Copy PR Review | ui_workbench | chat_ui | `tests/golden/` | Surfaces byte-identical SQL, Terraform, and LookML diffs for engineer PR approval. |
| DPF-05 | 5. Accept (Gate G4) | capability | multi_stack | `dpf/testing.py · framework/skills/register-knowledge-catalog/` | Runs live BigQuery assertions, captures human attestations, and publishes Catalog ports. |
| DPF-05-01 | Outbound Watermark Extractor | integration | cli_batch | `examples/sales_performance/extract/extract_postgres.py` | Extracts incremental source rows with lookback safety into append-only raw BigQuery. |
| DPF-05-02 | Quarantine Reject Ledger | crud_module | sql_pipeline | `framework/skills/transform-raw-to-staging/SKILL.md` | Routes invalid staging rows to _rejects relations and blocks partial publication. |
| DPF-05-03 | Live Acceptance Test Runner | business_function | cli_batch | `dpf/testing.py` | Executes automated BigQuery SQL assertions and static checks bound to build_digest. |
| DPF-05-04 | Domain Attestation Gate | ui_workbench | chat_ui | `dpf/testing.py` | Records Finance and domain expert sign-offs on non-SQL business truths at Gate G4. |
| DPF-05-05 | Knowledge Catalog Publisher | agent | adk_agent | `framework/skills/register-knowledge-catalog/SKILL.md` | Registers published ports, glossary EntryLinks, and 7 ADG-00 aspects in Catalog. |
| DPF-06 | 6. Monitor (Day 2 Loop) | capability | multi_stack | `dpf/monitor.py · framework/skills/monitor-data-product/` | Evaluates business-calendar SLOs and AGF estate alerts to open traced change proposals. |
| DPF-06-01 | Business-Calendar Monitor | business_function | cli_batch | `dpf/monitor.py` | Evaluates freshness, volume, and schema drift strictly during business working hours. |
| DPF-06-02 | AGF & Catalog Breach Feed | integration | cloud_service | `framework/contracts/run-evidence.v1.schema.json` | Ingests AGF lineage, ledger, and Knowledge Catalog scan alerts as run-evidence.v1. |
| DPF-06-03 | Build & Run Evidence Ledger | crud_module | cli_batch | `examples/evidence/sales_performance/` | Stores immutable test, attestation, and runtime health evidence per build digest. |
| DPF-06-04 | Change Proposal Workbench | ui_workbench | chat_ui | `openspec/changes/README.md` | Opens requirement-traced delta specs for human review when breaches or new needs arise. |
