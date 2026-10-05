# Changes

Work happens here as an OpenSpec change. Changes use the project's custom workflow schema
`data-product` (`openspec/schemas/data-product/`), so every change has the same artefacts:

```
openspec/changes/<change-id>/
├── .openspec.yaml     schema: data-product, created, goal, affected_areas (+ skip_specs)
├── proposal.md        why, what changes, capabilities, products, gates to re-run
├── specs/             delta specs (## ADDED / MODIFIED / REMOVED Requirements)
├── design.md          manifest elements changed; does the semantic digest change?
├── verification.md    each changed requirement mapped to a test id (dpf test plan)
├── operations.md      freshness, volume and drift impact; backfill or restatement
└── tasks.md           ends with dpf check <product> --gate G3 (and G4 after a deployed run)
```

```bash
openspec new change add-margin-measure --goal "Add a gross margin measure"   # schema from config.yaml
openspec status --change add-margin-measure          # which artefact is next, and what blocks it
openspec instructions proposal --change add-margin-measure   # template + project rules for one artefact
openspec validate add-margin-measure --strict
openspec archive add-margin-measure                  # after G3 (and G4) pass: merge deltas into specs/
```

## Which specs does your change touch?

| Change | BRD delta | TDD delta | Business re-approval |
|---|---|---|---|
| New measure or attribute requested | Yes | Yes | Yes |
| Grain or history behaviour changes | Yes | Yes | Yes: `semantics.md` is re-signed (`dpf signoff`) |
| Re-partitioning, reservation sizing, engine swap | No | Yes | No: engineering lead only |
| Methodology graduation with unchanged semantics | No | Yes | No |
| Operational fix after a monitor breach | No | No | No (`skip_specs: true`) |

A BRD version bump marks every dependent TDD, manifest and sign-off stale. Run
`dpf tdd stale` to find them.

## Changes opened by the monitor plane

`dpf monitor <product> --open-change` turns a breach of the observability policy into a
change named `monitor-<product>-<kind>-<YYYYMMDD-HHMM>` (kind: `freshness`, `volume`,
`check`, `schema-drift`, or `incident` for a mix). Its proposal quotes the breach (policy,
observed value, threshold, requirements at risk) and links the runbook sections.

It starts with `skip_specs: true` because an operational fix (re-run, backfill, accept a
reviewed schema change) changes no requirement. If the investigation shows a requirement
or decision must change, add delta specs and remove `skip_specs`; the change then goes
through the gates like any other.

The traceability matrix is generated, not stored here: `dpf trace <product>` writes
`generated/<product>/trace.{json,md}`.
