# Phase 4 — Memory, Learning, and Consolidation

Phase 4 gives Arena durable experience without requiring a vector database or an LLM call for every memory operation.

## Memory types

- **Episodic:** what happened during a task or interaction.
- **Semantic:** durable knowledge explicitly promoted from experience.
- **Procedural:** reusable experience about how to perform work; represented by the same durable store so a future skill system can consume it.
- **Lesson:** explicit lessons learned during reflection.

## Retrieval

`MemoryStore.search()` provides bounded lexical retrieval with importance weighting. This is intentionally cheap on local hardware. Embedding/vector retrieval can be added later as an optional layer rather than becoming a mandatory always-on service.

## Learning and consolidation

`MemoryLearner` records episodes and only promotes semantic facts or lessons when a caller explicitly supplies them. The system does not silently convert an LLM-generated interpretation into permanent truth.

## Reflection

`ReflectionEngine` provides an explicit boundary for post-task summaries, lessons, and unresolved questions. A reflection with no lesson remains a reflection; nothing is automatically invented.

## Runtime integration

`CognitiveRuntime` now owns `MemoryStore`, `MemoryLearner`, and `ReflectionEngine` alongside the Phase 3 world/belief/reasoning stack. All persistent cognitive data can share the existing SQLite database.

## Hardware strategy

The baseline implementation is CPU/SQLite based and does not require embeddings or a second database. This keeps background cognitive memory cheap on the 14900K / 16 GB RAM / 8 GB VRAM machine. Semantic retrieval, compression, and neural embeddings can be introduced selectively later.
