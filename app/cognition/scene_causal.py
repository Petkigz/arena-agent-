"""Causal and counterfactual replay for the deterministic scene model.

The replay path uses the existing causal graph representation for support
relations, then runs a side-effect-free physics intervention. Its output is a
prediction, never an observation or execution result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.cognition.causal_inference import (
    CausalEdge,
    CausalGraph,
    CausalNode,
    CausalRelationType,
)
from app.cognition.scene_graph import PhysicsPrediction, PhysicsSimulator, SceneGraph, SceneGraphError


@dataclass(frozen=True)
class SceneCounterfactual:
    baseline_digest: str
    predicted_digest: str
    target_object_id: str
    intervention: Dict[str, Any]
    prediction: PhysicsPrediction
    causal_paths: Tuple[Tuple[str, ...], ...]
    epistemic_status: str = "PREDICTED"
    observation_required: bool = True
    execution_performed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "baseline_digest": self.baseline_digest,
            "predicted_digest": self.predicted_digest,
            "target_object_id": self.target_object_id,
            "intervention": dict(self.intervention),
            "prediction": self.prediction.to_dict(),
            "causal_paths": [list(path) for path in self.causal_paths],
            "epistemic_status": self.epistemic_status,
            "observation_required": self.observation_required,
            "execution_performed": self.execution_performed,
        }


class SceneCausalReplay:
    """Build support-causal links and replay explicit scene interventions."""

    @staticmethod
    def support_graph(scene: SceneGraph) -> CausalGraph:
        graph = CausalGraph()
        for object_id in sorted(scene.objects):
            obj = scene.objects[object_id]
            graph.add_node(CausalNode(
                node_id=f"scene:{object_id}",
                name=object_id,
                description=f"scene object {obj.object_type} position/state",
                variable_type="continuous",
                metadata={"source": "scene_graph", "visibility": obj.visibility},
            ))
        for relation in scene.relations.values():
            if relation.relation_type != "supported_by":
                continue
            graph.add_edge(CausalEdge(
                edge_id=f"scene-support:{relation.source_id}:{relation.target_id}",
                source_id=f"scene:{relation.target_id}",
                target_id=f"scene:{relation.source_id}",
                relation_type=CausalRelationType.DIRECT_CAUSE,
                strength=1.0,
                confidence=relation.confidence,
                evidence=list(relation.evidence_ids),
                mechanism="support/contact constrains the supported object's vertical state",
                metadata={"simulated": True},
            ))
        return graph

    @classmethod
    def replay(
        cls,
        scene: SceneGraph,
        target_object_id: str,
        intervention: Dict[str, Any],
        *,
        steps: int = 1,
        dt: float = 0.1,
        gravity: float = 9.81,
    ) -> SceneCounterfactual:
        if target_object_id not in scene.objects:
            raise SceneGraphError(f"unknown scene object: {target_object_id}")
        allowed = {"x", "y", "vx", "vy", "support_id"}
        unknown = sorted(set(intervention) - allowed)
        if unknown:
            raise SceneGraphError(f"unsupported scene intervention fields: {unknown}")
        if not intervention:
            raise SceneGraphError("scene counterfactual requires an explicit intervention")

        counterfactual = scene.clone()
        target = counterfactual.object(target_object_id)
        changes: Dict[str, Any] = {}
        for field_name, value in intervention.items():
            if field_name in {"x", "y", "vx", "vy"}:
                try:
                    changes[field_name] = float(value)
                except (TypeError, ValueError) as exc:
                    raise SceneGraphError(f"intervention field {field_name} must be numeric") from exc
            else:
                changes[field_name] = value
        counterfactual.objects[target_object_id] = target.__class__(
            **{**target.to_dict(), **changes}
        )
        prediction = PhysicsSimulator.simulate(
            counterfactual, steps=steps, dt=dt, gravity=gravity
        )
        causal_graph = cls.support_graph(scene)
        paths: List[Tuple[str, ...]] = []
        target_node = f"scene:{target_object_id}"
        for node_id in sorted(causal_graph.nodes):
            if node_id == target_node:
                continue
            path = causal_graph.get_causal_path(target_node, node_id)
            if path:
                paths.append(tuple(path))
        return SceneCounterfactual(
            baseline_digest=scene.digest(),
            predicted_digest=prediction.scene.digest(),
            target_object_id=target_object_id,
            intervention=dict(intervention),
            prediction=prediction,
            causal_paths=tuple(paths),
        )
