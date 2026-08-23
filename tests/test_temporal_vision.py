"""Deterministic temporal visual tracking without identity or intent claims."""

from app.cognition.temporal_vision import TemporalVisionTracker, bbox_iou


def _det(label="person", x=0, y=0, width=100, height=100, confidence=0.9):
    return {
        "label": label,
        "confidence": confidence,
        "bbox": {"x": x, "y": y, "width": width, "height": height},
    }


def test_iou_is_deterministic():
    first = {"x": 0, "y": 0, "width": 100, "height": 100}
    same = dict(first)
    shifted = {"x": 50, "y": 0, "width": 100, "height": 100}
    assert bbox_iou(first, same) == 1.0
    assert round(bbox_iou(first, shifted), 3) == 0.333


def test_tracks_appearance_persistence_and_movement(tmp_path):
    tracker = TemporalVisionTracker(tmp_path / "vision.db", max_missing_frames=1)

    first = tracker.update_frame([_det()], source="desktop")
    track_id = first["tracks"][0]["track_id"]
    assert [event["event_type"] for event in first["events"]] == ["appeared"]

    stable = tracker.update_frame([_det(x=5)], source="desktop")
    assert stable["tracks"][0]["track_id"] == track_id
    assert stable["events"] == []
    assert stable["tracks"][0]["frame_count"] == 2

    moved = tracker.update_frame([_det(x=35)], source="desktop")
    assert moved["tracks"][0]["track_id"] == track_id
    assert [event["event_type"] for event in moved["events"]] == ["moved"]
    assert moved["events"][0]["evidence"]["normalized_displacement"] > 0


def test_disappearance_requires_configured_missing_frames(tmp_path):
    tracker = TemporalVisionTracker(tmp_path / "vision.db", max_missing_frames=1)
    appeared = tracker.update_frame([_det("chair")], source="desktop")
    track_id = appeared["tracks"][0]["track_id"]

    first_missing = tracker.update_frame([], source="desktop")
    assert first_missing["events"] == []
    second_missing = tracker.update_frame([], source="desktop")

    assert second_missing["events"][0]["event_type"] == "disappeared"
    assert second_missing["events"][0]["track_id"] == track_id
    assert second_missing["scene_summary"]["active_tracks"] == 0


def test_visual_streams_are_isolated(tmp_path):
    tracker = TemporalVisionTracker(tmp_path / "vision.db")
    desktop = tracker.update_frame([_det("person", x=0)], source="desktop")
    phone = tracker.update_frame([_det("person", x=0)], source="phone")

    assert desktop["tracks"][0]["track_id"] != phone["tracks"][0]["track_id"]
    assert tracker.scene_summary("desktop")["active_tracks"] == 1
    assert tracker.scene_summary("phone")["active_tracks"] == 1


def test_tracks_and_events_survive_restart(tmp_path):
    path = tmp_path / "vision.db"
    first_tracker = TemporalVisionTracker(path)
    first = first_tracker.update_frame([_det("car")], source="camera-1")
    track_id = first["tracks"][0]["track_id"]

    second_tracker = TemporalVisionTracker(path)
    next_frame = second_tracker.update_frame([_det("car", x=10)], source="camera-1")

    assert next_frame["tracks"][0]["track_id"] == track_id
    assert second_tracker.recent_events()[0]["event_type"] in {"appeared", "moved"}


def test_invalid_detections_are_ignored_without_fabricated_tracks(tmp_path):
    tracker = TemporalVisionTracker(tmp_path / "vision.db")
    result = tracker.update_frame([
        {"label": "person", "confidence": 0.9, "bbox": {}},
        {"label": "", "confidence": 0.9, "bbox": {"x": 0, "y": 0, "width": 1, "height": 1}},
        {"not": "a detection"},
    ], source="desktop")

    assert result["success"] is True
    assert result["detections_accepted"] == 0
    assert result["tracks"] == []
    assert result["events"] == []
