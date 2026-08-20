"""
Common Sense Knowledge Base for AGI

This module provides a comprehensive knowledge base containing 10,000+ facts about:
- Physical world (gravity, object permanence, physics)
- Human behavior (social norms, psychology, emotions)
- Causal relationships (cause and effect)
- Temporal relationships (before, after, during)
- Spatial relationships (left, right, above, below)

This is the foundation for AGI - without common sense, AI cannot understand the world.
"""

from .common_sense_knowledge_base import CommonSenseKnowledgeBase, CommonSenseFact

__all__ = ['CommonSenseKnowledgeBase', 'CommonSenseFact']
