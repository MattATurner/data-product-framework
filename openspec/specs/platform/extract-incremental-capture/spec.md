# Extract Incremental Capture Specification

## Purpose

Capture changes from a source system reliably, repeatably and replayably.

### Requirement: Capture mode suits the freshness need

#### Scenario: Sub-hourly freshness
- WHEN the BRD justifies freshness tighter than the source can bear under polling
- THEN change data capture SHALL be preferred over watermark batch.

### Requirement: Replay and backfill

#### Scenario: Re-running a past window
- WHEN a historical window is replayed
- THEN the result SHALL match the original load
- AND downstream models SHALL restate only the affected partitions.

### Requirement: Watermarks are durable

#### Scenario: Failure mid-batch
- WHEN extraction fails partway
- THEN the watermark SHALL NOT advance
- AND the next run SHALL resume without loss or duplication.

### Requirement: Source inspection prefers MCP

#### Scenario: Feasibility check during design
- WHEN the TDD verifies source metadata for a feasibility pass
- THEN an MCP server from the registry SHALL be used where one covers the source
- AND the tier SHALL be recorded on the source binding.
