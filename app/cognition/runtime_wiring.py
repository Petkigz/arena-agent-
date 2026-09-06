"""Phase-module wiring for the cognitive cycle (Phases 11-21).

Extracted verbatim from CognitiveRuntime._integrate_phase_modules
(composition refactor step 10d). The runtime delegates here; `rt` IS the
single authoritative CognitiveRuntime instance — this module holds no state
of its own and creates no second runtime. Each integration is best-effort:
failures are logged and never interrupt the cycle.
"""
from app.config import settings
from app.utils.logger import app_logger


def integrate_phase_modules(
    rt,
        user_text: str,
        intent_type: str,
        latency_ms: float,
        reasoning_action: str,
        success: bool,
        goal_verified: bool,
    ) -> None:
        """
        Wire the higher-order cognition modules (Phases 11-21) into the cognitive cycle.

        Each module contributes a non-fatal, best-effort observation: failures are logged
        but never interrupt the cycle. This is what turns the previously-orphaned modules
        (causal inference, strategic planning, social/cultural cognition, metacognition,
        consciousness, embodied cognition, cross-domain transfer, creative generation)
        into live parts of the closed loop.

        Write-path modules *learn* from this cycle; read-path modules expose self-knowledge
        onto the blackboard so subsequent reasoning can consult the agent's own state.
        """
        try:
            from app.cognition.metacognitive_monitor import CognitiveProcess, ReasoningStrategy
            rt.metacognitive_monitor.record_process(
                process_type=CognitiveProcess.REASONING,
                strategy=ReasoningStrategy.ABDUCTIVE,
                input_data={"user_text": user_text[:200], "intent": intent_type},
                output_data={"reasoning_action": reasoning_action, "success": success},
                execution_time_ms=round(latency_ms, 2),
                confidence=0.7,
                success=success,
                errors=[] if success else [f"Cycle ended in state '{reasoning_action}' without success"],
            )
        except Exception as e:
            app_logger.warning(f"Metacognitive integration failed: {e}")

        try:
            from app.cognition.causal_inference import CausalRelationType
            rt.causal_inference.add_causal_relationship(
                cause_name=f"intent:{intent_type}",
                effect_name="goal_verified" if goal_verified else "goal_unverified",
                relation_type=CausalRelationType.DIRECT_CAUSE,
                strength=0.8 if goal_verified else 0.2,
                confidence=0.6,
                evidence=[user_text[:80]],
                mechanism=f"Observed outcome of '{reasoning_action}' reasoning on '{intent_type}' tasks.",
            )
        except Exception as e:
            app_logger.warning(f"Causal inference integration failed: {e}")

        try:
            rt.blackboard.set(
                "strategic_overview",
                rt.strategic_planning.get_strategic_overview(),
                source="strategic_planning",
            )
        except Exception as e:
            app_logger.warning(f"Strategic planning integration failed: {e}")

        try:
            rt.blackboard.set(
                "transfer_summary",
                rt.cross_domain_transfer.get_transfer_summary(),
                source="cross_domain_transfer",
            )
        except Exception as e:
            app_logger.warning(f"Cross-domain transfer integration failed: {e}")

        try:
            if goal_verified:
                rt.blackboard.set(
                    "creativity_summary",
                    rt.creative_generation.get_creativity_summary(),
                    source="creative_generation",
                )
            else:
                # On failure, generate creative alternatives for subsequent replanning.
                ideas = rt.creative_generation.generate_ideas(
                    problem=user_text,
                    context={"intent": intent_type},
                    num_ideas=3,
                )
                rt.blackboard.set(
                    "creative_alternatives",
                    [i.description for i in ideas],
                    source="creative_generation",
                )
        except Exception as e:
            app_logger.warning(f"Creative generation integration failed: {e}")

        try:
            from app.cognition.social_cognition import MentalState, SocialNorm, Emotion
            rt.social_cognition.infer_mental_state(
                agent_id="owner",
                state_type=MentalState.INTENTION,
                content=user_text[:100],
                evidence=[f"user message: {user_text[:80]}"],
                confidence=0.6,
                perspective_agent_id="arena",
                belief_chain=["arena", "owner"],
            )
            # P2 AGI: Infer emotion from text cues (real signal, not just rule-based response)
            # Human intelligence detects frustration, joy, sadness from language
            lower = user_text.lower()
            emotion_map = {
                "joy": (["happy", "great", "wonderful", "excited", "love", "awesome"], Emotion.JOY),
                "sadness": (["sad", "down", "depressed", "unhappy", "lonely", "miss"], Emotion.SADNESS),
                "anger": (["angry", "frustrated", "annoyed", "mad", "hate", "furious", "irritated"], Emotion.ANGER),
                "fear": (["scared", "afraid", "worried", "anxious", "nervous", "fear"], Emotion.FEAR),
                "surprise": (["wow", "surprised", "amazing", "unexpected", "incredible"], Emotion.SURPRISE),
            }
            for emo_name, (keywords, emo_enum) in emotion_map.items():
                if any(k in lower for k in keywords):
                    intensity = 0.7 if any(k in lower for k in ["very", "really", "so", "extremely"]) else 0.5
                    rt.social_cognition.recognize_emotion(
                        agent_id="owner",
                        primary_emotion=emo_enum,
                        intensity=intensity,
                        triggers=[f"emotion keyword '{emo_name}' in: {user_text[:60]}"],
                    )
                    rt.social_cognition.infer_mental_state(
                        agent_id="owner",
                        state_type=MentalState.EMOTION,
                        content=f"owner feels {emo_name} (from text)",
                        evidence=[f"keyword in: {user_text[:60]}"],
                        confidence=0.65,
                        perspective_agent_id="arena",
                        belief_chain=["arena", "owner"],
                    )
                    break

            rt.social_cognition.record_interaction(
                participants=["owner", "arena"],
                interaction_type="task",
                context=user_text[:100],
                norms_followed=[SocialNorm.COOPERATION],
                norms_violated=[],
                emotional_outcomes={},
                outcome="positive" if goal_verified else "neutral",
            )
        except Exception as e:
            app_logger.warning(f"Social cognition integration failed: {e}")

        try:
            from app.cognition.consciousness_simulation import QualiaType
            rt.consciousness.create_experience(
                qualia_type=QualiaType.COGNITIVE,
                content=f"Processed '{intent_type}' task ({reasoning_action})",
                intensity=0.6,
                valence=0.3 if goal_verified else -0.2,
                arousal=0.5,
                clarity=0.7,
                duration_ms=latency_ms,
                associated_thoughts=[f"intent={intent_type}", f"verified={goal_verified}"],
            )
        except Exception as e:
            app_logger.warning(f"Consciousness integration failed: {e}")

        try:
            rt.blackboard.set(
                "embodied_summary",
                rt.embodied_cognition.get_embodied_summary(),
                source="embodied_cognition",
            )
        except Exception as e:
            app_logger.warning(f"Embodied cognition integration failed: {e}")

        try:
            rt.cultural_learning.record_observed_behavior(
                agent_id="owner",
                behavior_type=intent_type,
                description=user_text[:100],
                context="cognitive_cycle",
                outcome="success" if goal_verified else "failure",
            )
        except Exception as e:
            app_logger.warning(f"Cultural learning integration failed: {e}")

        try:
            # Phase 14: resource/multi-agent/knowledge/uncertainty self-report.
            rt.blackboard.set(
                "phase14_report",
                rt.advanced_cognition.get_phase14_report(),
                source="advanced_cognition",
            )
            # Phase 14: calibrate confidence against the actual outcome (learning).
            rt.advanced_cognition.uncertainty_quantifier.calibrate_confidence(
                predictions=[0.7],
                actual=[1.0 if goal_verified else 0.0],
            )
        except Exception as e:
            app_logger.warning(f"Advanced cognition integration failed: {e}")

        try:
            # Phase 22: ground the utterance to perception/action/meaning.
            grounding = rt.language_grounding.ground_utterance(user_text)
            rt.blackboard.set("utterance_grounding", grounding, source="language_grounding")
        except Exception as e:
            app_logger.warning(f"Language grounding integration failed: {e}")

        # P1-1 AGI: Perception → Grounding loop — if a recent screenshot exists,
        # run object/face detection and auto-create perceptual groundings so words
        # like 'person', 'face', 'chair' become grounded to real visual features.
        # Best-effort, rate-limited (max once per 60s to save CPU), never raises.
        try:
            from pathlib import Path
            import time as _time
            from app.tools.object_detector import ObjectDetectorTool

            # Rate limit: don't run detection every cycle (CPU heavy)
            now = _time.time()
            last = getattr(rt, "_last_grounding_detection_ts", 0)
            if now - last >= 60:
                screenshots_dir = settings.DATA_DIR / "workspace" / "screenshots"
                if screenshots_dir.exists():
                    latest = None
                    latest_mtime = 0
                    for p in screenshots_dir.glob("*.png"):
                        try:
                            mtime = p.stat().st_mtime
                            if mtime > latest_mtime:
                                latest_mtime = mtime
                                latest = p
                        except Exception:
                            continue
                    if latest and (_time.time() - latest_mtime) < 300:  # only if recent (<5 min)
                        det_res = ObjectDetectorTool.analyze_image_grounded(str(latest), auto_create_groundings=True)
                        if det_res.get("success"):
                            detections = det_res.get("detections", [])
                            temporal = rt.temporal_vision.update_frame(
                                detections,
                                source="desktop_screen",
                            )
                            rt.blackboard.set(
                                "temporal_visual_scene",
                                temporal,
                                source="temporal_vision",
                            )
                            for event in temporal.get("events", [])[:20]:
                                try:
                                    rt.world_ingest.ingest(
                                        subject=event.get("track_id", event.get("label", "visual_object")),
                                        predicate="visual_event",
                                        value={
                                            "event_type": event.get("event_type"),
                                            "label": event.get("label"),
                                            "bbox": event.get("current_bbox"),
                                        },
                                        source="temporal_vision",
                                        observation_type="inferred",
                                        confidence=float(event.get("confidence", 0.0)),
                                    )
                                except Exception:
                                    pass
                            if detections:
                                rt.blackboard.set(
                                    "grounded_detections",
                                    {
                                        "image": str(latest),
                                        "detections": detections,
                                        "groundings_created": det_res.get("groundings_created", []),
                                        "engine": det_res.get("engine", "unknown"),
                                        "temporal_events": temporal.get("events", []),
                                    },
                                    source="object_detector",
                                )
                                app_logger.info(
                                    f"Grounded detections: {len(detections)} objects from {latest.name} "
                                    f"→ {len(det_res.get('groundings_created', []))} groundings, "
                                    f"{len(temporal.get('events', []))} temporal event(s)"
                                )
                rt._last_grounding_detection_ts = now
        except Exception as e:
            app_logger.warning(f"Perception→grounding loop failed (best-effort): {e}")
