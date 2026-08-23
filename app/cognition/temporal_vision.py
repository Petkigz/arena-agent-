"""Deterministic temporal object tracking across visual frames.

Consumes grounded detector outputs (label, confidence, bbox), assigns persistent
track IDs by label + IoU, and emits appeared/moved/disappeared events. It makes no
identity, depth, intent, or emotion claims.
"""

from __future__ import annotations

import json
import math
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from app.config import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bbox(value: Any) -> Optional[Dict[str, float]]:
    if not isinstance(value, dict):
        return None
    try:
        box = {
            "x": float(value.get("x", 0)),
            "y": float(value.get("y", 0)),
            "width": max(0.0, float(value.get("width", 0))),
            "height": max(0.0, float(value.get("height", 0))),
        }
        return box if box["width"] > 0 and box["height"] > 0 else None
    except (TypeError, ValueError):
        return None


def bbox_iou(first: Dict[str, float], second: Dict[str, float]) -> float:
    left = max(first["x"], second["x"])
    top = max(first["y"], second["y"])
    right = min(first["x"] + first["width"], second["x"] + second["width"])
    bottom = min(first["y"] + first["height"], second["y"] + second["height"])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    union = (
        first["width"] * first["height"]
        + second["width"] * second["height"]
        - intersection
    )
    return intersection / union if union > 0 else 0.0


def _center(box: Dict[str, float]) -> Tuple[float, float]:
    return box["x"] + box["width"] / 2.0, box["y"] + box["height"] / 2.0


@dataclass
class VisualTrack:
    track_id: str
    label: str
    stream_id: str
    bbox: Dict[str, float]
    confidence: float
    first_seen: str
    last_seen: str
    frame_count: int = 1
    missed_frames: int = 0
    active: bool = True


@dataclass
class VisualEvent:
    event_id: str
    event_type: str  # appeared | moved | disappeared
    track_id: str
    label: str
    timestamp: str
    frame_id: str
    previous_bbox: Optional[Dict[str, float]]
    current_bbox: Optional[Dict[str, float]]
    confidence: float
    evidence: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TemporalVisionTracker:
    def __init__(
        self,
        db_path: Optional[str | Path] = None,
        *,
        iou_match_threshold: float = 0.3,
        movement_iou_threshold: float = 0.7,
        max_missing_frames: int = 2,
    ) -> None:
        self.db_path = str(db_path or (settings.DATA_DIR / "temporal_vision.db"))
        self.iou_match_threshold = max(0.05, min(0.95, iou_match_threshold))
        self.movement_iou_threshold = max(
            self.iou_match_threshold, min(0.99, movement_iou_threshold)
        )
        self.max_missing_frames = max(0, min(20, int(max_missing_frames)))
        self._lock = threading.RLock()
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS visual_tracks (
                track_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                stream_id TEXT NOT NULL DEFAULT 'default',
                bbox_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                frame_count INTEGER NOT NULL,
                missed_frames INTEGER NOT NULL,
                active INTEGER NOT NULL
            )""")
            track_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(visual_tracks)").fetchall()
            }
            if "stream_id" not in track_columns:
                conn.execute(
                    "ALTER TABLE visual_tracks ADD COLUMN stream_id TEXT NOT NULL DEFAULT 'default'"
                )
            conn.execute("""CREATE TABLE IF NOT EXISTS visual_frames (
                frame_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                detections_json TEXT NOT NULL
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS visual_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                track_id TEXT NOT NULL,
                label TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                frame_id TEXT NOT NULL,
                previous_bbox_json TEXT,
                current_bbox_json TEXT,
                confidence REAL NOT NULL,
                evidence_json TEXT NOT NULL
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_visual_tracks_stream_active ON visual_tracks(stream_id, active, label)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_visual_events_time ON visual_events(timestamp)")
            conn.commit()

    @staticmethod
    def _track(row: sqlite3.Row) -> VisualTrack:
        return VisualTrack(
            track_id=row["track_id"], label=row["label"], stream_id=row["stream_id"],
            bbox=json.loads(row["bbox_json"]), confidence=float(row["confidence"]),
            first_seen=row["first_seen"], last_seen=row["last_seen"],
            frame_count=int(row["frame_count"]), missed_frames=int(row["missed_frames"]),
            active=bool(row["active"]),
        )

    def _active_tracks(self, stream_id: str) -> List[VisualTrack]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM visual_tracks WHERE active = 1 AND stream_id = ? ORDER BY first_seen",
                (stream_id,),
            ).fetchall()
            return [self._track(row) for row in rows]

    def _save_track(self, track: VisualTrack) -> None:
        with self._connect() as conn:
            conn.execute("""INSERT OR REPLACE INTO visual_tracks
                (track_id, label, stream_id, bbox_json, confidence, first_seen,
                 last_seen, frame_count, missed_frames, active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                track.track_id, track.label, track.stream_id,
                json.dumps(track.bbox), track.confidence,
                track.first_seen, track.last_seen, track.frame_count,
                track.missed_frames, int(track.active),
            ))
            conn.commit()

    def _save_event(self, event: VisualEvent) -> None:
        with self._connect() as conn:
            conn.execute("""INSERT INTO visual_events VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                event.event_id, event.event_type, event.track_id, event.label,
                event.timestamp, event.frame_id,
                json.dumps(event.previous_bbox) if event.previous_bbox else None,
                json.dumps(event.current_bbox) if event.current_bbox else None,
                event.confidence, json.dumps(event.evidence),
            ))
            conn.commit()

    def update_frame(
        self,
        detections: List[Dict[str, Any]],
        *,
        source: str = "unknown",
        timestamp: Optional[str] = None,
        frame_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        timestamp = timestamp or _now()
        frame_id = frame_id or f"frame_{uuid4().hex[:12]}"
        stream_id = str(source or "default")[:500]
        normalized = []
        for detection in detections or []:
            box = _bbox(detection.get("bbox")) if isinstance(detection, dict) else None
            label = str(detection.get("label", "")).strip().lower() if isinstance(detection, dict) else ""
            if not label or box is None:
                continue
            try:
                confidence = max(0.0, min(1.0, float(detection.get("confidence", 0.0))))
            except (TypeError, ValueError):
                confidence = 0.0
            normalized.append({"label": label, "bbox": box, "confidence": confidence})

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO visual_frames VALUES (?, ?, ?, ?)",
                    (frame_id, source, timestamp, json.dumps(normalized)),
                )
                conn.commit()

            tracks = self._active_tracks(stream_id)
            unmatched_track_ids = {track.track_id for track in tracks}
            events: List[VisualEvent] = []
            frame_tracks = []

            for detection in sorted(
                normalized,
                key=lambda item: (item["label"], -item["confidence"], item["bbox"]["x"]),
            ):
                candidates = [
                    (bbox_iou(track.bbox, detection["bbox"]), track)
                    for track in tracks
                    if track.track_id in unmatched_track_ids and track.label == detection["label"]
                ]
                candidates.sort(key=lambda item: (-item[0], item[1].track_id))
                best_iou, track = candidates[0] if candidates else (0.0, None)

                if track is None or best_iou < self.iou_match_threshold:
                    track = VisualTrack(
                        track_id=f"track_{uuid4().hex[:12]}",
                        label=detection["label"],
                        stream_id=stream_id,
                        bbox=detection["bbox"],
                        confidence=detection["confidence"],
                        first_seen=timestamp,
                        last_seen=timestamp,
                    )
                    event = VisualEvent(
                        event_id=f"ve_{uuid4().hex[:12]}", event_type="appeared",
                        track_id=track.track_id, label=track.label, timestamp=timestamp,
                        frame_id=frame_id, previous_bbox=None, current_bbox=track.bbox,
                        confidence=track.confidence,
                        evidence={"source": source, "match_iou": 0.0},
                    )
                    events.append(event)
                else:
                    unmatched_track_ids.remove(track.track_id)
                    previous_bbox = dict(track.bbox)
                    previous_center = _center(previous_bbox)
                    current_center = _center(detection["bbox"])
                    displacement = math.dist(previous_center, current_center)
                    normalizer = max(1.0, math.hypot(
                        previous_bbox["width"], previous_bbox["height"]
                    ))
                    normalized_displacement = displacement / normalizer
                    track.bbox = detection["bbox"]
                    track.confidence = round(
                        track.confidence * 0.6 + detection["confidence"] * 0.4, 4
                    )
                    track.last_seen = timestamp
                    track.frame_count += 1
                    track.missed_frames = 0
                    if (
                        best_iou < self.movement_iou_threshold
                        and normalized_displacement >= 0.1
                    ):
                        events.append(VisualEvent(
                            event_id=f"ve_{uuid4().hex[:12]}", event_type="moved",
                            track_id=track.track_id, label=track.label,
                            timestamp=timestamp, frame_id=frame_id,
                            previous_bbox=previous_bbox, current_bbox=track.bbox,
                            confidence=track.confidence,
                            evidence={
                                "source": source,
                                "match_iou": round(best_iou, 4),
                                "normalized_displacement": round(normalized_displacement, 4),
                            },
                        ))

                self._save_track(track)
                frame_tracks.append({
                    "track_id": track.track_id,
                    "label": track.label,
                    "bbox": track.bbox,
                    "confidence": track.confidence,
                    "frame_count": track.frame_count,
                })

            for track in tracks:
                if track.track_id not in unmatched_track_ids:
                    continue
                track.missed_frames += 1
                if track.missed_frames > self.max_missing_frames:
                    track.active = False
                    events.append(VisualEvent(
                        event_id=f"ve_{uuid4().hex[:12]}", event_type="disappeared",
                        track_id=track.track_id, label=track.label,
                        timestamp=timestamp, frame_id=frame_id,
                        previous_bbox=track.bbox, current_bbox=None,
                        confidence=track.confidence,
                        evidence={"source": source, "missed_frames": track.missed_frames},
                    ))
                self._save_track(track)

            for event in events:
                self._save_event(event)
            self._prune_history()

        return {
            "success": True,
            "frame_id": frame_id,
            "source": source,
            "detections_accepted": len(normalized),
            "tracks": frame_tracks,
            "events": [event.to_dict() for event in events],
            "scene_summary": self.scene_summary(stream_id),
        }

    def _prune_history(self, max_frames: int = 5000, max_events: int = 10000) -> None:
        with self._connect() as conn:
            conn.execute("""DELETE FROM visual_frames WHERE frame_id IN (
                SELECT frame_id FROM visual_frames ORDER BY timestamp DESC LIMIT -1 OFFSET ?
            )""", (max_frames,))
            conn.execute("""DELETE FROM visual_events WHERE event_id IN (
                SELECT event_id FROM visual_events ORDER BY timestamp DESC LIMIT -1 OFFSET ?
            )""", (max_events,))
            conn.execute("""DELETE FROM visual_tracks WHERE active = 0 AND track_id IN (
                SELECT track_id FROM visual_tracks WHERE active = 0
                ORDER BY last_seen DESC LIMIT -1 OFFSET 10000
            )""")
            conn.commit()

    def recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM visual_events ORDER BY timestamp DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [
            VisualEvent(
                event_id=row["event_id"], event_type=row["event_type"],
                track_id=row["track_id"], label=row["label"], timestamp=row["timestamp"],
                frame_id=row["frame_id"],
                previous_bbox=json.loads(row["previous_bbox_json"]) if row["previous_bbox_json"] else None,
                current_bbox=json.loads(row["current_bbox_json"]) if row["current_bbox_json"] else None,
                confidence=float(row["confidence"]), evidence=json.loads(row["evidence_json"]),
            ).to_dict()
            for row in rows
        ]

    def scene_summary(self, stream_id: str = "default") -> Dict[str, Any]:
        tracks = self._active_tracks(stream_id)
        by_label: Dict[str, int] = {}
        for track in tracks:
            by_label[track.label] = by_label.get(track.label, 0) + 1
        return {
            "stream_id": stream_id,
            "active_tracks": len(tracks),
            "objects_by_label": by_label,
            "tracks": [asdict(track) for track in tracks[:50]],
        }
