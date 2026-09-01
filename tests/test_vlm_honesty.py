"""Owner review item 9 (2026-09-01, P2): VLM isn't actually running —
the vision chain is screenshot → OCR → LLM (the fallback), not
image → VLM reasoning.

Status per the owner: 🟡 capability incomplete, NOT broken. The
fallback is intentional and honest at the tool level. What must change
is the CLAIMS: nothing may assert full visual reasoning while the
live engine is the OCR+LLM fallback, and the engine basis must be
visible wherever vision is claimed (tool listing, capability ladder,
per-call results).

Standing honesty constraints: heuristics/descriptions are named for
what they actually measure; the basis is visible in the output;
regression tests verify the measurement itself.
"""

from unittest.mock import patch

from app.tools.vlm_analyzer import VlmAnalyzerTool


# ── vlm_status: the honest status contract ──────────────────────────────

def test_vlm_status_unavailable_reports_fallback_engine_and_reason():
    """When the VLM is not installed, the status must SAY so: engine is
    the fallback, and the note names the fallback plus the install path.
    'VLM available=False' is a complete answer only because the basis
    travels with it."""
    with patch.object(VlmAnalyzerTool, "is_available", return_value=False):
        status = VlmAnalyzerTool.get_status()
    assert status["available"] is False
    assert status["engine"] == "fallback:ocr_llm"
    assert "OCR+LLM" in status["note"]
    assert "moondream2" in status["note"].lower()


def test_vlm_status_available_reports_vlm_engine():
    """The discriminator is real: with the VLM present the engine is
    vlm:<id> — the fallback labeling is not vacuous."""
    with patch.object(VlmAnalyzerTool, "is_available", return_value=True):
        status = VlmAnalyzerTool.get_status()
    assert status["available"] is True
    assert status["engine"].startswith("vlm:")


# ── vlm_analyze: per-call engine labeling (never claim VLM when the
#    OCR+LLM fallback ran) ───────────────────────────────────────────────

def test_vlm_analyze_fallback_labels_the_engine_honestly(tmp_path):
    """With no VLM, an analysis that succeeds via the fallback must carry
    engine 'fallback:*' and a note saying the VLM was unavailable — a
    'vlm:*' engine string on an OCR+LLM result would be a false claim
    of visual reasoning."""
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    fake_fallback = {
        "success": True,
        "ai_analysis": "The screen shows a code editor.",
        "ocr_text": "def main(): pass",
        "detections": [],
        "detection_engine": "ocr_llm",
    }
    with patch.object(VlmAnalyzerTool, "_ensure_model",
                      classmethod(lambda cls: (None, None))), \
         patch("app.tools.vision_analyzer.VisionAnalyzerTool.analyze_screen_image",
               return_value=fake_fallback):
        res = VlmAnalyzerTool.analyze_image(str(img))
    assert res["success"] is True
    assert str(res.get("engine", "")).startswith("fallback:")
    assert "OCR+LLM" in str(res.get("note", ""))
    assert "vlm_analysis" in res  # the analysis text is present


def test_vlm_analyze_vlm_engine_labeled_when_vlm_runs(tmp_path):
    """When a VLM model IS loaded, the result engine is vlm:<id> — the
    two paths are distinguishable in the output."""
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")

    class FakeVLM:
        def encode_image(self, img_arg):
            return "embeds"

        def answer_question(self, embeds, prompt, tokenizer):
            return "A red circle on white background."

    with patch.object(VlmAnalyzerTool, "_ensure_model",
                      classmethod(lambda cls: (FakeVLM(), object()))), \
         patch.object(VlmAnalyzerTool, "_model_id", "fake-vlm"), \
         patch("PIL.Image.open"):
        res = VlmAnalyzerTool.analyze_image(str(img))
    assert res["success"] is True
    assert str(res.get("engine", "")).startswith("vlm:")
    assert res.get("vlm_analysis") == "A red circle on white background."


# ── the claim surfaces: tool listing + capability ladder ────────────────

def test_manifest_description_names_the_fallback():
    """The tool listing is a claim surface: vlm_analyze's description
    must state that visual reasoning is CONDITIONAL on the VLM being
    installed and name the OCR+LLM fallback — no unconditional
    'true visual understanding' claim while the fallback is the live
    engine."""
    from app.cognition.tool_registry import capability_entry
    entry = capability_entry("vlm_analyze")
    assert entry is not None
    desc = str(entry.get("description", "")).lower()
    assert "fallback" in desc
    assert "ocr" in desc
    # The unconditional claim must be gone.
    assert "true visual understanding" not in desc


def test_capability_ladder_evidence_names_the_fallback():
    """vision.analyze is what the capability resolver maps 'Image
    scanning capability' onto — its ladder evidence must name the
    OCR+LLM fallback, not just 'VLM vision tools' (which implies the
    VLM is what runs)."""
    from app.cognition.runtime import CognitiveRuntime
    backing = CognitiveRuntime.NATIVE_CAPABILITY_BACKING.get("vision.analyze")
    assert backing is not None
    evidence = str(backing.get("evidence", "")).lower()
    assert "ocr" in evidence
    assert "fallback" in evidence
