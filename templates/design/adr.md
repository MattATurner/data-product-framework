---
id: ADR-<DOMAIN>-<nnn>-<nn>
title: <The decision in a few words>
status: proposed              # proposed | accepted | superseded
date: '<YYYY-MM-DD>'
scope: product
product: <product_id>
decides: <area>               # methodology | capture | engine | storage | materialisation | grain | orchestration | conformance
---

# ADR-{DOMAIN}-{nnn}-{nn}: {The decision in a few words}

<!--
ADR template · Design stage · Data Product Framework

Write an ADR when the design leaves a default in registry/platform-defaults.yaml, or when
it needs bespoke code (tool tier 5). Then:

1. Save it as products/{product_id}/adr/ADR-{DOMAIN}-{nnn}-{nn}-{short-name}.md.
2. List the id under `adrs:` in product.yaml.
3. Cite it on the decision line in the TDD: **ADR:** ADR-{DOMAIN}-{nnn}-{nn}.

A methodology departure needs `decides: methodology`, because G1 looks for it. Bespoke code
must say why tiers 1 to 4 (MCP servers, managed agents and APIs, SDKs) do not work. The
worked examples are in products/sales_performance/adr/.

Replace every {placeholder} below and every <placeholder> in the front matter. The front
matter is YAML, where a value that starts with a brace is read as a mapping. Delete these
comments when you finish.
-->

## Context

{The BRD requirements and source facts that force a decision. Cite the ids (R-n, AG-n,
HB-n) and the feasibility finding.}

## Options considered

| Option | Serves the requirements? | Cost and risk |
|---|---|---|
| {The platform default} | {Yes, partly or no, and which requirement it misses} | {…} |
| {The chosen option} | {…} | {…} |

## Decision

{What is decided, in one or two sentences.}

## Consequences

{What the design gains and gives up, what the business must be told in semantics.md, and
when to review the decision.}
