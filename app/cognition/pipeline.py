"""Compatibility names for the single authoritative cognitive pipeline.

Keep legacy import paths without a second wrapper implementation or execution.
"""

from app.cognition.cognitive_pipeline import CognitivePipeline as CognitivePipeline

PipelineBridge = CognitivePipeline

__all__ = ["CognitivePipeline", "PipelineBridge"]
