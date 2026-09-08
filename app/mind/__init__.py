"""Beanie Mind — Phase 1 of the AGI roadmap (docs/AGI_ROADMAP.md).

The canonical entry point of the one artificial mind. BeanieMind is NOT a
second cognitive runtime: it wraps the existing CognitiveRuntime singleton
(invariant #1, one brain always) and adds what the runtime lacks today:

- an *identity* ("I am Beanie") — persisted, owner-visible state, not a
  prompt string (M1);
- a unified *internal state* view (BeanieState skeleton, M2);
- ONE named door — :meth:`BeanieMind.process` — through which every input
  (voice, WS text, REST, later observation/autonomy) enters the same mind.

Everything else in the repository remains something the Mind can call.
"""

from app.mind.identity import BeanieIdentity
from app.mind.state import BeanieState
from app.mind.beanie_mind import BeanieMind, MODALITIES
from app.mind.world_facade import WorldModelFacade, WORLD_ENTITY_TYPES
from app.mind.self_facade import SelfModelFacade
from app.mind.memory_facade import UnifiedMemory, SocialMemoryStore, MetaMemory
from app.mind.world_first import WorldFirstReasoning
from app.mind.learning_loop import GeneralLearningEngine, EXPERIENCE_KINDS
from app.mind.teaching import DemonstrationTeaching
from app.mind.media_learning import MediaLearning

__all__ = [
    "BeanieMind", "BeanieIdentity", "BeanieState", "MODALITIES",
    "WorldModelFacade", "WORLD_ENTITY_TYPES", "SelfModelFacade",
    "UnifiedMemory", "SocialMemoryStore", "MetaMemory", "WorldFirstReasoning",
    "GeneralLearningEngine", "EXPERIENCE_KINDS", "DemonstrationTeaching",
    "MediaLearning",
]
