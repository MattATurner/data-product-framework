# Changes

Work happens here as an OpenSpec change, carrying delta specs against a product's
`brd/` and/or `tdd/` spec.

```
openspec/changes/<change-id>/
├── proposal.md     why, scope, affected consumers
├── specs/          delta specs (## ADDED / MODIFIED / REMOVED Requirements)
├── tasks.md        build breakdown
└── trace.md        generated traceability matrix
```

## Which specs does your change touch?

| Change | BRD delta | TDD delta | Business re-approval |
|---|---|---|---|
| New measure or attribute requested | Yes | Yes | Yes |
| Grain or history behaviour changes | Yes | Yes | Yes — `semantics.md` is re-signed |
| Re-partitioning, reservation sizing, engine swap | No | Yes | No — engineering lead only |
| Methodology graduation with unchanged semantics | No | Yes | No |

A BRD version bump marks every dependent TDD stale. Run `dpf tdd stale` to find them.
