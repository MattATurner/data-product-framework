---
id: ADR-019
title: Symbiotic integration with the Agentic Data Governance Framework (ADG-00)
status: accepted
date: 2026-11-06
scope: platform
decides: governance
---

# ADR-019: Symbiotic integration with the Agentic Data Governance Framework (ADG-00)

## Context

Enterprise data governance spans two complementary operational planes:

1. **Build-time product specification and compilation:** turning an approved business
   requirement (`BRD`) into a deterministic technical design (`TDD`), SQL transformations,
   column-level policy tags, semantic Explores, data quality assertions, and signed
   business semantics before any code reaches production.
2. **Continuous run-time estate assurance:** inspecting newly landed raw tables at `T=0`
   with Sensitive Data Protection, auto-quarantining unowned or unclassified tables,
   reconciling runtime OpenLineage execution against declared lineage, mediating
   time-bounded purpose-based consumer access (`180d`/`360d`), reconciling pooled General
   Ledger balances, running schema-breakage blast-radius dry runs, governing multi-year
   retention with cryptographic tombstones, and scanning cloud projects for ungoverned
   shadow assets.

Embedding continuous estate scanners, Sensitive Data Protection workers, chat approval
workflows, or CDMC `C1–C14` scoring engines inside `dpf` would duplicate the **Agentic
Data Governance Framework (`AGF` / `ADG-00`)** and compromise `dpf`'s role as a fast,
zero-daemon, deterministic build-time compiler. Conversely, leaving `dpf` and `AGF`
unconnected forces governance agents to reverse-engineer product ownership, grain,
business purpose, and Critical Data Element (`CDE`) intent that `dpf` already knows at
compile time.

## Decision

1. **Symbiotic separation of planes (Build-Time Factory vs. Run-Time Estate Guardian).**
   `dpf` owns the build-time product lifecycle (`Discover & Prioritise -> Describe -> Design
   -> Build -> Accept -> Monitor`). `AGF` (`ADG-01` through `ADG-05` running on Gemini
   Platform and subscribing to Knowledge Catalog change feeds) owns continuous run-time
   estate controls across EDM Council CDMC `C1–C14`. Neither framework embeds or duplicates
   the other's runtime.
2. **BigQuery Knowledge Catalog is the zero-coupling contract bus.**
   `dpf` and `AGF` exchange state through Knowledge Catalog Business Glossaries,
   `EntryLink` column bindings, and the seven canonical `ADG-00` Single-Writer Aspect
   Types:
   - `governance-ownership-v1` (`CDMC C2` accountable owner and technical steward)
   - `catalog-registration-v1` (`CDMC C3/C5` authoritative provisioning point, ports, and
     authorised `C8` purpose codes)
   - `sensitivity-classification-v1` (`CDMC C6` column sensitivity tiers and policy-tag
     masking bindings)
   - `cde-financial-governance-v1` (`ADG DC-2` Critical Data Element glossary bindings and
     General Ledger reconciliation flags)
   - `lineage-governance-v1` (`CDMC C14` compiled design-time lineage edges for runtime
     OpenLineage verification)
   - `data-product-quality-v1` (`CDMC C12` blocking quality gate posture, Knowledge Catalog
     quality scan references, and freshness SLOs)
   - `retention-lifecycle-v1` (`ADG DL-1 / CDMC C11` retention window, legal hold defaults,
     sovereign region allowlist, and human-gated cryptographic tombstone mode)

   When a product declares `governance.agf.enabled: true` in `product.yaml`,
   `dpf generate` deterministically populates `agf_aspects` in `catalog-registration.json`
   (`catalog-registration.v1`).
3. **Compile-time enforcement of `AGF` sensitivity and residency signals at Gate `G1`.**
   When `governance.agf` is enabled:
   - Every column classified as `RESTRICTED` (either imported from `ADG-01`'s `T=0`
     Sensitive Data Protection scan via `governance.agf.classified_columns` or bound to a
     `classification: restricted` Business Glossary term) MUST be covered by a
     `governance.policy_tags` column-masking rule on semantic models (`silver` and `gold`).
   - External `sharing_listing` output ports (`BigQuery sharing`) MUST NEVER expose any
     `RESTRICTED` column, directly or inherited from upstream models, even if masked
     internally.
   - When `governance.agf.allowed_regions` is declared, `G1` verifies `deployment.region`
     and every `deployment.environments[*].region` remain within the authorised sovereign
     regions (`CDMC C1/C10`).
4. **Closed-loop run-time feedback (`AGF -> DPF`).**
   Run-time lineage drift (`ADG-02`), General Ledger reconciliation variances (`ADG-03`),
   or schema blast-radius alerts emit `run-evidence.v1` breaches so
   `dpf monitor --open-change` opens an OpenSpec change proposal citing the affected `BRD`
   requirement. Ungoverned shadow tables or LookML projects discovered by `ADG-05` onboard
   into `dpf` via `dpf proto import-dataform` or `dpf proto import-looker`.

## Consequences

- `dpf` gains enterprise-grade CDMC `C1–C14` governance alignment with zero additional
  Python dependencies or background daemons.
- Products that do not enable `governance.agf` incur zero manifest or artefact changes;
  products operating in `AGF`-governed estates emit machine-verifiable `ADG-00` aspects
  and catch `RESTRICTED` column leaks and region drift at `G1` before deployment.
