# Kimball dimensional

**Status:** available; not the default.

## When this is the right answer

- Several sources must agree on shared entities.
- Self-service BI consumers who need conformed, reusable dimensions.
- Numbers must reconcile across domains.
- Consumers need attribution "as at the time", not just current state.

If none of those apply, use `direct` — a star schema nobody needed is a cost with no
benefit.

## The four-step design process

This drives the BRD interview, not just the build:

1. Select the business process.
2. Declare the grain.
3. Identify the dimensions.
4. Identify the facts.

Steps 2 to 4 are *derived* in the TDD from business-language answers. The business is
never asked to state a grain.

## Core concepts

- Conformed dimensions, governed by the bus matrix in `registry/conformance.yaml`.
- Surrogate keys; natural keys retained for lineage.
- SCD types 1, 2, 3 and 6; unknown members; late-arriving members.
- Fact types: transaction, periodic snapshot, accumulating snapshot, factless.
