---
skill_id: author-brd
implements: brd-completeness
consumes: null
produces: brd.yaml
tool_tier: 4
tool: local
owner: business SME, facilitated
---

# Author a BRD

Interview the business against the rubric. **You are facilitating, not authoring.**

## Hard rules

1. **No modelling vocabulary.** Never write grain, SCD, dimension, surrogate key,
   partition, or a warehouse product name into a BRD.
2. **Never invent an answer.** If it is unknown, record `[NEEDS-DECISION: id]` with an
   owner, due date, default assumption and blast radius.
3. **Capture what they asked for verbatim**, then ask the rubric questions around it.

## Interview order

Groups A to K of the rubric, plus the elicitation questions contributed by the active
methodology pack (`brd_elicitation_questions` in its `methodology.yaml`).

| Ask this | It quietly determines |
|---|---|
| "What is the finest level of detail you need to drill down to?" | grain |
| "Could two rows ever describe the same thing?" | grain columns |
| "If a customer moves segment, should last quarter's figures move with them?" | history semantics |
| "Must your numbers agree with another team's?" | conformance |
| "Can these figures be added across months? Regions?" | additivity |
| "How late can a correction arrive?" | restatement window |
| "If something is cancelled, should it disappear or stay visible?" | retention and exclusion |
| "Roughly how many people will use this, how often?" | materialisation |
| "Will anything other than your BI tool read this?" | storage format |

## Source-anchored answers

Business analysts often answer with source field names. When that happens, record the
field as **evidence**, and ask: *"What question does that field answer for you?"* The
answer is the requirement.

## Output

`brd/spec.md` (requirements + acceptance examples) and `brd/brd.yaml` (structured half).
Then run `dpf brd validate`.
