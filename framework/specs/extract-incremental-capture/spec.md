# Extract Incremental Capture Specification

## Purpose

Capture changes from a source system reliably, repeatably and replayably.

## Requirements

### Requirement: Capture mode suits the freshness need
The capture mode SHALL be chosen from the justified freshness need and the source's
reachability, and SHALL be one the source registry lists as supported now.

#### Scenario: Sub-hourly freshness
- **WHEN** the BRD justifies freshness tighter than the source can bear under polling
- **THEN** change data capture SHALL be preferred over watermark batch

#### Scenario: Unsupported capture mode
- **WHEN** the manifest asks for a capture mode the source cannot currently support
- **THEN** G1 SHALL fail and the constraint SHALL be raised to the business

### Requirement: Durable watermarks
A watermark SHALL advance only in the same atomic unit of work that lands the batch and its
manifest.

#### Scenario: Failure mid-batch
- **WHEN** extraction or landing fails partway
- **THEN** the watermark SHALL NOT advance
- **AND** a retry SHALL NOT land the same batch twice

### Requirement: No loss from late commits
Extraction SHALL re-read a configured look-back window before the watermark, and staging SHALL
deduplicate re-read rows so that each source version appears exactly once after staging.

#### Scenario: Long-running source transaction
- **WHEN** a row commits with a change timestamp earlier than the last watermark
- **THEN** it SHALL be captured by the look-back window
- **AND** SHALL appear once in staging

### Requirement: Source inspection prefers MCP
Feasibility inspection SHALL use a registered MCP server where one covers the source.

#### Scenario: Feasibility check during design
- **WHEN** the TDD verifies source metadata for a feasibility pass
- **THEN** an MCP server from the registry SHALL be used where one covers the source
- **AND** the tier SHALL be recorded on the source binding
