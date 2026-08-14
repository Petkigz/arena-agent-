# Phase 3 — Evidence, Beliefs, and Closed-Loop Reasoning

Phase 3 adds a lightweight reasoning substrate without requiring an LLM call for every state update.

## Flow

```text
Observation -> Evidence -> competing hypotheses -> decision
                                      ^                 |
                                      |                 v
                                new evidence <- investigation/tool
```

## Components

- `beliefs.py`: evidence provenance, source reliability, freshness decay, persistent beliefs, contradiction visibility.
- `hypotheses.py`: competing explanations remain alive instead of collapsing uncertainty into one fact.
- `confidence.py`: empirical source reliability calibration from observed outcomes.
- `belief_engine.py`: deterministic evidence aggregation and hypothesis reconstruction.
- `information_gain.py`: explicit information needs with priorities and target propositions.
- `reasoning_cycle.py`: cheap decision gate: answer, investigate, act, or defer.
- `action_selection.py`: semantic information needs map only to registered tools; unknown tools are rejected.
- `reasoning_loop.py`: bounded observe -> reason -> investigate -> observe loop with cognitive-state and event-bus integration.
- `runtime.py`: composition root for an isolated cognitive stack.

## Design constraints

1. Beliefs are revisable hypotheses, not immutable facts.
2. Contradictory evidence is retained rather than discarded.
3. Stale evidence can lose influence through half-life decay.
4. Tool execution is allowlisted through explicit registration.
5. The cognitive loop is bounded to avoid runaway investigation.
6. Deterministic bookkeeping stays local and cheap; deeper semantic reasoning can be delegated to the LLM later.
7. SQLite is used for persistence so the stack remains practical on constrained local hardware.

## Example

```python
runtime = CognitiveRuntime()
runtime.actions.registry.register("chrome", planner)
runtime.executor.register("process_probe", probe)
trace = runtime.loop.run(...)
```

The trace contains decisions, investigation plans, tool results, and a terminal reason, making the loop inspectable and testable.
