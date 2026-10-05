# Architecture decision records

Platform decisions live here; product decisions live in `products/<product>/adr/`.
Every ADR has front-matter with `id`, `title`, `status`, `date`, `scope` and, where it
records a choice dpf can check, `decides` (for example `methodology` or `capture`).

`dpf` uses ADRs mechanically:

- G1 fails when a layer departs from the platform default methodology and the product
  lists no ADR with `decides: methodology`.
- Every ADR id listed in a product manifest (`adrs:`) or cited by a TDD decision must exist.
- `dpf lint` fails a tier-5 skill or a bespoke code file whose `adr=` marker names no ADR.

| ADR | Decision | Status |
|---|---|---|
| [ADR-001](ADR-001-transform-engine.md) | Transform engine | accepted |
| [ADR-002](ADR-002-storage-format.md) | Storage format | accepted |
| [ADR-003](ADR-003-orchestrator.md) | Orchestrator | accepted |
| [ADR-004](ADR-004-cdc-apply-strategy.md) | CDC apply strategy | accepted |
| [ADR-005](ADR-005-skill-runtime.md) | Skill runtime | accepted |
| [ADR-006](ADR-006-spec-granularity.md) | Spec granularity | accepted |
| [ADR-007](ADR-007-product-versioning.md) | Product versioning | accepted |
| [ADR-008](ADR-008-brd-authorship.md) | BRD authorship and ownership | accepted |
| [ADR-009](ADR-009-provisional-promotion.md) | Provisional promotion policy | accepted |
| [ADR-010](ADR-010-conformance-authority.md) | Conformance authority | proposed |
| [ADR-011](ADR-011-methodology-plane.md) | Methodology plane | accepted |
| [ADR-012](ADR-012-two-specs-per-product.md) | Two specs per product | accepted |
| [ADR-013](ADR-013-grain-derived-then-confirmed.md) | Grain is derived, then confirmed | accepted |
| [ADR-014](ADR-014-materialisation-strategy.md) | Materialisation strategy | accepted |
| [ADR-015](ADR-015-outbound-watermark-extractor.md) | Outbound-only watermark extractor | accepted |
