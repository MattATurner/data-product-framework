---
skill_id: compose-pipeline
implements: compose-pipeline
consumes: product.yaml
produces: skill DAG
tool_tier: 4
tool: local
---

# Compose the skill DAG

Resolve the manifest into an ordered chain and prove it before anything runs.

## Steps

1. Read `product.yaml`: sources, layers, methodology, engine, storage.
2. Select skills per layer from the core catalogue plus the active methodology pack.
3. **Type-check every handoff** — the produced contract must satisfy the next consumed contract.
4. **Check methodology x engine support** for every role.
5. Emit the ordered DAG.

## Must

- Fail with both contract ids named on a mismatch. Never generate a partial pipeline.
- Be deterministic: same manifest, same DAG, same artefacts.
