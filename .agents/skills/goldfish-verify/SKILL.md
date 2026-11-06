---
name: goldfish-verify
description: >-
  Run zero-context ("Goldfish") subagent verification passes at G0 (define), G1 (design blind
  playback) and G3 (build SQL and assertion critique) to catch semantic drift, conversational
  anchoring and offline SQL traps that deterministic `dpf check` gates cannot see. Use before
  business sign-off (`dpf signoff`), after `dpf brd validate` on a co-drafted BRD, or before
  accepting `--update-golden` when custom SQL or acceptance cases changed.
metadata:
  # Workspace-only for now. Before moving this skill into skills/, add the platform capability
  # spec openspec/specs/platform/semantic-verification: dpf validate requires it.
  dpf:
    skill_id: goldfish-verify
    stage: design
    scope: product
    implements: semantic-verification
    consumes: []
    produces: []
    tool_tier: 4
    tool: dpf-local
    owner: data-engineer
---

# Verify with a zero-context Goldfish

Deterministic gates (`dpf brd validate`, `dpf check`) verify contracts, vocabulary, ID
traceability and byte-identical generation. They cannot tell when a long-lived coding-agent
session ("the Elephant") has anchored on earlier chat history—echoing what the BRD *asked for*
in `playback.md` (`semantics.md`) while `product.yaml` or `products/<id>/sql/*.sql` quietly
does something else, or writing an acceptance query that compiles cleanly and passes on zero
rows.

Based on Google's [Elephant-Goldfish Model](https://github.com/google/elephant-goldfish-model),
this skill spawns a **fresh, zero-memory subagent ("the Goldfish")** given **only** the
artefacts under test and **none** of the conversation that produced them.

## Hard isolation rules

1. **Always use a fresh subagent.** Spawn a new subagent context (`invoke_subagent` in
   Antigravity / Jetski—setting `Model: "flash"` where workspace subagent rules require it—or
   `Task` in Claude Code). Never simulate a Goldfish inside the session that drafted the BRD,
   TDD, manifest or SQL; if the host cannot create fresh subagents, stop and report that
   stateless verification was skipped.
2. **Enforce strict reading lists.** Pass only the file paths listed for the chosen gate.
   Instruct the Goldfish explicitly which directories it **must not** read.
3. **Never write into `openspec/specs/` or `tests/golden/`.** Write Goldfish reports only under
   `generated/<product>/` (gitignored).
4. **Sceptical, plain-English posture.** Instruct every Goldfish to lead with defects and
   unstated assumptions, avoid praise or filler, and write findings in plain English.

---

## Pass G0 · Define (`define` — cold BRD ambiguity check)

Run after `dpf brd validate <product>` passes mechanically, when the BRD was co-authored or
edited in a multi-turn session.

- **Goldfish may read:**
  - `openspec/specs/products/<domain>/<product>/brd/spec.md` and `brd.yaml`
  - `registry/brd-rubric.yaml`, `registry/brd-vocabulary.yaml` and `registry/glossary.yaml`
    (plus any `registry_overlay` glossary)
- **Goldfish must NOT read:** `tdd/`, `products/<product>/`, `examples/`, `generated/`, or
  chat history.
- **Goldfish checks:**
  1. Figures or terms whose calculation, exclusion rule or denominator could mean two things to
     two teams (even if present in the glossary).
  2. Restatement windows, late-arriving corrections, cancellations or returns left implicit in
     any `AX-*` scenario.
  3. Solutioneering phrased in business words that still pre-empts design without using a
     blocked technical keyword.
- **Output:** `generated/<product>/goldfish-g0.md`, phrasing each gap as a plain-English
  question for the business owner (`[NEEDS-DECISION]`), never an invented rule.

---

## Pass G1 · Design (`design` — blind reverse-playback check)

Run after `product.yaml` and `tdd/playback.md` (`tdd/semantics.md`) are drafted, **before**
running `dpf signoff`.

- **Step 1 — Blind Goldfish reconstruction:**
  - **Goldfish may read ONLY:**
    - `products/<product>/product.yaml`
    - `products/<product>/sql/*.sql` (if any)
    - `products/<product>/lookml/*.lookml` (if any)
    - `registry/platform-defaults.yaml`, `registry/foundations.yaml` and `registry/glossary.yaml`
      (plus `registry_overlay`)
  - **Goldfish must NOT read:** `openspec/specs/` (`brd/` and `tdd/`, including
    `playback.md` / `semantics.md`), `products/<product>/acceptance.yaml`, or chat history.
  - **Prompt task:** Restate in plain business English (zero SQL, cloud or modelling jargon)
    what this data product actually delivers: one row per what, how historical changes and
    as-at joins behave (including start-of-day or go-live cut-offs), what gets quarantined or
    excluded, how fresh figures are, who can see masked vs unmasked values, and — when Looker
    Explores or Dashboards are declared — which KPIs, filters and drill paths business users
    actually see and whether metric filter rules (such as cancelled-line exclusions) match the
    underlying tables. Write the blind reconstruction to `generated/<product>/goldfish-playback.md`.
- **Step 2 — Elephant reconciliation:**
  - In the parent session, compare `generated/<product>/goldfish-playback.md` against both
    `brd/brd.yaml` (`brd/spec.md`) and `tdd/playback.md` (`tdd/semantics.md`).
  - Any behaviour where the blind playback differs from the BRD or is missing from
    `tdd/playback.md` (`tdd/semantics.md`) is a **G1 semantic defect**: fix `product.yaml` /
    `sql/*.sql`, update `tdd/playback.md`, or raise a Feasibility Finding against the BRD
    before recording `dpf signoff`.

---

## Pass G3 · Build (`build` — offline SQL & assertion critic)

Run after `dpf generate <product>` succeeds, before accepting `dpf generate <product> --update-golden`
whenever `products/<product>/sql/*.sql`, `products/<product>/acceptance.yaml` or Tier-5 code
changed.

- **Goldfish may read ONLY:**
  - `products/<product>/product.yaml` and `products/<product>/acceptance.yaml`
  - `products/<product>/sql/*.sql`
  - `generated/<product>/` (`dataform/` or `dbt/`, `terraform/`, `test-spec.json`)
- **Goldfish must NOT read:** `openspec/specs/products/*/brd/`, `tests/golden/`, or chat
  history.
- **Goldfish checks (offline blind spots `compile`, `parse` and `validate` miss):**
  1. **Dialect & execution traps:** `SELECT` alias collisions inside `GROUP BY` / `HAVING` /
     `QUALIFY` (such as aggregate-of-aggregate errors in BigQuery), unsafe casts, or timezone
     truncation mismatches against `business_timezone`.
  2. **Grain & NULL safety:** Joins in `products/<product>/sql/*.sql` that can multiply a
     model's declared `grain_columns` on 1-to-many matches or silently drop rows on nullable
     join predicates.
  3. **Vacuous acceptance assertions (`AT-*`):** Queries in `acceptance.yaml` /
     `test-spec.json` that return zero failing rows when the source or target table is empty,
     or that test tautologies rather than falsifiable business invariants.
  4. **Silent staging drops & engine-agent leakage:** SQL bodies in `products/<product>/sql/*.sql`
     (especially those drafted or imported via Dataform's Data Engineering Agent) that silently
     filter out bad rows with `WHERE` or inline `QUALIFY` before `<model>_rejects` quarantine,
     or leak engine-specific `${ref(...)}` / `${when(...)}` syntax.
  5. **Cross-tool first-apply ordering:** Resources in `generated/<product>/terraform/` (such
     as Knowledge Catalog quality scans or Dataform release schedules) that depend on tables
     or service constraints created only after the first pipeline run.
  6. **LookML join fanout & dashboard parity:** When `generated/<product>/semantic_layer/lookml/`
     is present, inspect `.view.lkml`, `.explore.lkml` and `.dashboard.lookml` for `one_to_many`
     join fanouts missing symmetric-aggregate keys, measures whose filters diverge from gold SQL
     views, or dashboard tiles whose labels misstate what the queried measure computes.
- **Output:** `generated/<product>/goldfish-g3.md` listing findings by severity (`Blocking`,
  `Should fix`, `Note`) with exact file paths and SQL/HCL snippets.
