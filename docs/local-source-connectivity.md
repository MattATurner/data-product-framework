# Connecting a local source to Google Cloud

Written for the reference implementation, whose Oracle instance runs on a developer
workstation. The principle generalises to any source behind a corporate network.

## The constraint

**Direction of connection decides the architecture.** A workstation behind corporate NAT
can reach out to Google Cloud over HTTPS, but Google Cloud cannot reach in. Every
managed extraction service — Datastream included — needs a route *to* the database.

| | Direction needed | Works from a desk? |
|---|---|---|
| Datastream CDC | GCP ➜ database | **No**, not without a tunnel |
| Dataflow JDBC template | Worker ➜ database | Only if the worker is on the same network |
| Local pull to GCS/BigQuery | Database ➜ GCP | **Yes** — outbound HTTPS |
| MCP Toolbox for Databases | Local process ➜ database | **Yes** — runs beside the database |

## Options, honestly compared

### A. Local pull, watermark batch — recommended to start

A process on the workstation reads via JDBC and writes to GCS or BigQuery over outbound
HTTPS. No inbound route, no tunnel, no firewall change.

- **Proves the whole framework chain end to end** — extract, land, model, publish, catalog.
- Capture mode is `watermark`, so freshness is bounded by the schedule.
- **Not CDC**: deletes are invisible unless the source soft-deletes, and intra-interval
  changes collapse to the latest state.

### B. Reverse SSH tunnel, then Datastream CDC

The workstation opens an outbound SSH session to a Compute Engine bastion with a public
IP, using remote port forwarding. Datastream then uses its forward-SSH connectivity
method to reach the database through that bastion.

- Gives genuine CDC, including deletes.
- The tunnel is a long-lived process on a workstation — fine for a demo, unsuitable as a
  dependency for anything that must keep running.
- Still requires the Oracle CDC prerequisites: ARCHIVELOG mode, supplemental logging,
  LogMiner privileges.

### C. VPN or Cloud Interconnect

The production answer. Out of proportion for a proof.

## Recommended sequence

1. **Prove the framework with option A.** Watermark batch from the local Oracle. Every
   gate, every contract, every skill exercised, with no network dependency.
2. **Add CDC later via option B**, if and only if the business requirement needs it.

## How the framework should record this

This is exactly what the feasibility pass exists for. If the BRD justifies freshness that
only CDC can meet, the constraint is **not** an engineering shortcut taken quietly — it is
raised as a business-language issue against the BRD:

> *"Orders can be refreshed hourly today. Refreshing within minutes needs a network
> connection into the source database that does not exist yet. Is hourly acceptable for
> now?"*

The answer becomes a recorded decision: either the BRD relaxes its freshness requirement,
or connectivity work is scheduled and the TDD notes the interim state. Both outcomes are
visible in `semantics.md` and the traceability matrix. Neither is a silent compromise.

## Source inspection needs none of this

`mcp-toolbox-databases` runs **locally**, beside the database, using the JDBC URL. That
gives the agent tier-2 access to real schemas, keys and row counts for the TDD feasibility
pass — before any data movement is designed. Inspect first, then choose the capture mode.
