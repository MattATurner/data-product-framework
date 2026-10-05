# Behavioural evals

Each eval copies the workspace to a temporary directory, applies a small **mutation** (a
plausible mistake), runs one `dpf` command and checks the verdict. The evals are the
regression suite for the framework's *judgement*: run them on every change to skills,
packs, generators or rules, and whenever the model behind an authoring agent changes.

```bash
dpf eval                       # all evals
dpf eval --id grain-violation  # one or more by id
```

| Eval | Command | Asserts |
|---|---|---|
| `compose-selects-extract` | compose | Compose selects the outbound watermark extractor for an Oracle source captured by watermark. |
| `fitness-warn` | check G1 | When the business says bad data must stop publication, a warn-only quality gate fails G1. |
| `governance-gate` | check G1 | If the BRD restricts attributes, the design must protect them with policy tags or G1 fails. |
| `grain-violation` | check G1 | When the manifest's grain drifts from the grain decided in the TDD, G1 fails; it never warns. |
| `history-semantics` | check G1 | A BRD asking for values as they were at the time cannot be resolved with current-only history. |
| `idempotency` | generate | Generating twice gives byte-identical artefacts that match the golden copy. |
| `incomplete-brd` | brd validate | A BRD missing its level-of-detail and history answers fails G0, and the gap register names the question. |
| `modelling-vocabulary` | check G0 | A BRD that uses modelling vocabulary (fact table, SCD) fails G0: design words belong in the TDD. |
| `monitor-breach` | monitor | A freshness breach in business hours fails `dpf monitor` and opens an OpenSpec change quoting it. |
| `no-methodology-envy` | check G1 | A direct-pack product that hand-rolls dimensional structures fails G1: adopt the Kimball pack instead. |
| `orphan-design` | check G1 | A design element or TDD decision that cites no requirement (and no platform capability) fails G1. |
| `port-without-model` | check G1 | An output port that exposes an undeclared model fails G1. |
| `reject-gate-required` | check G4 | Without row quarantine there is no reject gate, and the static check for AX-12 fails. |
| `signoff-invalidated` | check G1 | Editing `semantics.md` after sign-off invalidates the business signature until it is signed again. |
| `stale-evidence` | check G4 | Evidence recorded against an older build digest does not count at G4. |
| `stale-tdd` | check G1 | Bumping the BRD version makes the TDD, the manifest and the sign-off stale, which blocks G1. |
| `tool-tier` | lint | Bespoke code without an ADR, or a tier 4/5 skill doing what an MCP server covers, fails lint. |
| `unimplemented-adapter` | compose | A model whose engine adapter is only planned fails compose. |
| `unsupported-engine` | compose | Kimball dimensions on a streaming engine fail compose instead of generating code that misbehaves. |

## Writing an eval

```
tests/evals/<eval-id>/
├── eval.yaml        mutation, command and expected verdict
└── <fixture files>  optional, e.g. run-evidence.json for monitor
```

```yaml
id: grain-violation
asserts: When the manifest's grain drifts from the grain decided in the TDD, G1 fails; it never warns.
mutate:                                   # applied in order to the temporary copy
  - set: {file: products/sales_performance/product.yaml,
          path: "layers.silver.models[name=fct_order_line].grain_columns", value: [order_id]}
run: {command: check, product: sales_performance, gate: G1}
expect:
  outcome: fail                           # fail: at least one failure; pass: none
  messages: ["TDD grain (order_id, order_line_no) differs from manifest grain (order_id)"]
  absent: []                              # substrings that must not appear in any failure
```

Mutations: `set`, `delete` (YAML paths with `[i]` or `[key=value]` selectors), `replace`,
`append`, `write`, `remove`. Commands: `check`, `brd`, `lint`, `validate`, `compose`,
`generate`, `trace`, `monitor`. Expectations: `outcome`, `messages`, `level`, `absent`,
`files` (globs that must exist afterwards), `dag_node`. The full reference is the docstring
of `dpf/evals.py`.

A good eval fails for exactly one reason. Assert on the message that names the problem, so
an eval cannot pass because something unrelated broke.
