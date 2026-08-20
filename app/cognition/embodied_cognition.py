"""
Phase 20: Embodied Cognition

Enables the agent to understand and interact with the physical world through:
1. Sensorimotor integration - connecting perception and action
2. Spatial reasoning - understanding 3D space and relationships
3. Physical interaction - modeling object manipulation
4. Embodied learning - learning through physical interaction
5. Motor planning - planning physical actions

This brings the agent closer to human-like understanding by grounding cognition in physical experience.
"""

import sqlite3
import json
import math
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import uuid
from app.utils.logger import app_logger


def _now() -> str:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


class SpatialRelation(Enum):
    """Types of spatial relationships."""
    ABOVE = "above"
    BELOW = "below"
    LEFT = "left"
    RIGHT = "right"
    FRONT = "front"
    BACK = "back"
    INSIDE = "inside"
    OUTSIDE = "outside"
    NEAR = "near"
    FAR = "far"
    TOUCHING = "touching"
    CONTAINS = "contains"


class ActionType(Enum):
    """Types of physical actions."""
    GRASP = "grasp"
    RELEASE = "release"
    PUSH = "push"
    PULL = "pull"
    LIFT = "lift"
    PLACE = "place"
    ROTATE = "rotate"
    MOVE = "move"
    TOUCH = "touch"
    POINT = "point"


class SensorType(Enum):
    """Types of sensors."""
    VISUAL = "visual"
    TACTILE = "tactile"
    PROPRIOCEPTIVE = "proprioceptive"
    AUDITORY = "auditory"
    DEPTH = "depth"
    FORCE = "force"


@dataclass
class Vector3D:
    """3D vector for spatial representation."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return {'x': self.x, 'y': self.y, 'z': self.z}
    
    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> 'Vector3D':
        """Create from dictionary."""
        return cls(x=data.get('x', 0.0), y=data.get('y', 0.0), z=data.get('z', 0.0))
    
    def distance_to(self, other: 'Vector3D') -> float:
        """Calculate distance to another point."""
        return math.sqrt(
            (self.x - other.x) ** 2 +
            (self.y - other.y) ** 2 +
            (self.z - other.z) ** 2
        )
    
    def __add__(self, other: 'Vector3D') -> 'Vector3D':
        """Add two vectors."""
        return Vector3D(self.x + other.x, self.y + other.y, self.z + other.z)
    
    def __sub__(self, other: 'Vector3D') -> 'Vector3D':
        """Subtract two vectors."""
        return Vector3D(self.x - other.x, self.y - other.y, self.z - other.z)
    
    def magnitude(self) -> float:
        """Calculate vector magnitude."""
        return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)
    
    def normalize(self) -> 'Vector3D':
        """Return normalized vector."""
        mag = self.magnitude()
        if mag == 0:
            return Vector3D(0, 0, 0)
        return Vector3D(self.x / mag, self.y / mag, self.z / mag)


@dataclass
class PhysicalObject:
    """A physical object in the environment."""
    object_id: str = field(default_factory=lambda: f"obj_{uuid.uuid4().hex[:8]}")
    name: str = ""
    object_type: str = ""  # e.g., "cup", "book", "chair"
    position: Vector3D = field(default_factory=Vector3D)
    orientation: Vector3D = field(default_factory=Vector3D)  # Euler angles
    dimensions: Vector3D = field(default_factory=Vector3D)  # Width, height, depth
    mass: float = 0.0  # kg
    color: str = ""
    material: str = ""
    graspable: bool = False
    movable: bool = False
    properties: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'object_id': self.object_id,
            'name': self.name,
            'object_type': self.object_type,
            'position': self.position.to_dict(),
            'orientation': self.orientation.to_dict(),
            'dimensions': self.dimensions.to_dict(),
            'mass': self.mass,
            'color': self.color,
            'material': self.material,
            'graspable': self.graspable,
            'movable': self.movable,
            'properties': self.properties,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PhysicalObject':
        """Create from dictionary."""
        return cls(
            object_id=data['object_id'],
            name=data.get('name', ''),
            object_type=data.get('object_type', ''),
            position=Vector3D.from_dict(data.get('position', {})),
            orientation=Vector3D.from_dict(data.get('orientation', {})),
            dimensions=Vector3D.from_dict(data.get('dimensions', {})),
            mass=data.get('mass', 0.0),
            color=data.get('color', ''),
            material=data.get('material', ''),
            graspable=data.get('graspable', False),
            movable=data.get('movable', False),
            properties=data.get('properties', {}),
            timestamp=data.get('timestamp', _now())
        )


@dataclass
class SensorReading:
    """A reading from a sensor."""
    reading_id: str = field(default_factory=lambda: f"reading_{uuid.uuid4().hex[:8]}")
    sensor_type: SensorType = SensorType.VISUAL
    data: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'reading_id': self.reading_id,
            'sensor_type': self.sensor_type.value,
            'data': self.data,
            'confidence': self.confidence,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SensorReading':
        """Create from dictionary."""
        return cls(
            reading_id=data['reading_id'],
            sensor_type=SensorType(data['sensor_type']),
            data=data.get('data', {}),
            confidence=data.get('confidence', 1.0),
            timestamp=data.get('timestamp', _now())
        )


@dataclass
class MotorAction:
    """A planned or executed motor action."""
    action_id: str = field(default_factory=lambda: f"action_{uuid.uuid4().hex[:8]}")
    action_type: ActionType = ActionType.MOVE
    target_object_id: Optional[str] = None
    start_position: Vector3D = field(default_factory=Vector3D)
    end_position: Vector3D = field(default_factory=Vector3D)
    parameters: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    success: bool = True
    errors: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'action_id': self.action_id,
            'action_type': self.action_type.value,
            'target_object_id': self.target_object_id,
            'start_position': self.start_position.to_dict(),
            'end_position': self.end_position.to_dict(),
            'parameters': self.parameters,
            'duration_ms': self.duration_ms,
            'success': self.success,
            'errors': self.errors,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MotorAction':
        """Create from dictionary."""
        return cls(
            action_id=data['action_id'],
            action_type=ActionType(data['action_type']),
            target_object_id=data.get('target_object_id'),
            start_position=Vector3D.from_dict(data.get('start_position', {})),
            end_position=Vector3D.from_dict(data.get('end_position', {})),
            parameters=data.get('parameters', {}),
            duration_ms=data.get('duration_ms', 0.0),
            success=data.get('success', True),
            errors=data.get('errors', []),
            timestamp=data.get('timestamp', _now())
        )


@dataclass
class SpatialRelationship:
    """A spatial relationship between two objects."""
    relationship_id: str = field(default_factory=lambda: f"rel_{uuid.uuid4().hex[:8]}")
    object1_id: str = ""
    object2_id: str = ""
    relation_type: SpatialRelation = SpatialRelation.NEAR
    distance: float = 0.0
    confidence: float = 1.0
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'relationship_id': self.relationship_id,
            'object1_id': self.object1_id,
            'object2_id': self.object2_id,
            'relation_type': self.relation_type.value,
            'distance': self.distance,
            'confidence': self.confidence,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SpatialRelationship':
        """Create from dictionary."""
        return cls(
            relationship_id=data['relationship_id'],
            object1_id=data['object1_id'],
            object2_id=data['object2_id'],
            relation_type=SpatialRelation(data['relation_type']),
            distance=data.get('distance', 0.0),
            confidence=data.get('confidence', 1.0),
            timestamp=data.get('timestamp', _now())
        )


class EmbodiedCognitionEngine:
    """
    Engine for embodied cognition and physical interaction.
    
    Provides methods for:
    - Managing physical objects in the environment
    - Processing sensor readings
    - Planning and executing motor actions
    - Reasoning about spatial relationships
    - Learning from physical interactions
    """
    
    def __init__(self, db_path: str = "data/embodied_cognition.db"):
        """Initialize the embodied cognition engine."""
        self.db_path = db_path
        self._ensure_db()
        self.agent_position = Vector3D(0, 0, 0)
        self.agent_orientation = Vector3D(0, 0, 0)
        app_logger.info(f"Embodied Cognition Engine initialized (db: {db_path})")
    
    def _ensure_db(self) -> None:
        """Ensure database tables exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS physical_objects (
                    object_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    object_data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sensor_readings (
                    reading_id TEXT PRIMARY KEY,
                    sensor_type TEXT NOT NULL,
                    reading_data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS motor_actions (
                    action_id TEXT PRIMARY KEY,
                    action_type TEXT NOT NULL,
                    action_data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS spatial_relationships (
                    relationship_id TEXT PRIMARY KEY,
                    object1_id TEXT NOT NULL,
                    object2_id TEXT NOT NULL,
                    relationship_data TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (object1_id) REFERENCES physical_objects(object_id),
                    FOREIGN KEY (object2_id) REFERENCES physical_objects(object_id)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_objects_type
                ON physical_objects(json_extract(object_data, '$.object_type'))
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_readings_type
                ON sensor_readings(sensor_type)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_actions_type
                ON motor_actions(action_type)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_relationships_objects
                ON spatial_relationships(object1_id, object2_id)
            """)
            
            conn.commit()
    
    def add_object(
        self,
        name: str,
        object_type: str,
        position: Vector3D,
        orientation: Vector3D = None,
        dimensions: Vector3D = None,
        mass: float = 0.0,
        color: str = "",
        material: str = "",
        graspable: bool = False,
        movable: bool = False,
        properties: Dict[str, Any] = None
    ) -> PhysicalObject:
        """
        Add a physical object to the environment.
        
        Args:
            name: Object name
            object_type: Type of object (e.g., "cup", "book")
            position: 3D position
            orientation: 3D orientation (Euler angles)
            dimensions: Object dimensions (width, height, depth)
            mass: Object mass in kg
            color: Object color
            material: Object material
            graspable: Whether the object can be grasped
            movable: Whether the object can be moved
            properties: Additional properties
        
        Returns:
            PhysicalObject object
        """
        obj = PhysicalObject(
            name=name,
            object_type=object_type,
            position=position,
            orientation=orientation or Vector3D(),
            dimensions=dimensions or Vector3D(),
            mass=mass,
            color=color,
            material=material,
            graspable=graspable,
            movable=movable,
            properties=properties or {}
        )
        
        self._save_object(obj)
        
        app_logger.info(
            f"Added object: {name} ({object_type}) at position "
            f"({position.x:.2f}, {position.y:.2f}, {position.z:.2f})"
        )
        
        return obj
    
    def update_object_position(
        self,
        object_id: str,
        new_position: Vector3D,
        new_orientation: Vector3D = None
    ) -> Optional[PhysicalObject]:
        """
        Update an object's position and/or orientation.
        
        Args:
            object_id: Object ID
            new_position: New position
            new_orientation: New orientation (optional)
        
        Returns:
            Updated PhysicalObject or None if not found
        """
        obj = self.get_object(object_id)
        if not obj:
            app_logger.error(f"Object {object_id} not found")
            return None
        
        obj.position = new_position
        if new_orientation:
            obj.orientation = new_orientation
        obj.timestamp = _now()
        
        self._save_object(obj)
        
        app_logger.info(
            f"Updated object {obj.name} position to "
            f"({new_position.x:.2f}, {new_position.y:.2f}, {new_position.z:.2f})"
        )
        
        return obj
    
    def get_object(self, object_id: str) -> Optional[PhysicalObject]:
        """Get an object by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT object_data FROM physical_objects WHERE object_id = ?",
                (object_id,)
            )
            row = cursor.fetchone()
            
            if row:
                object_data = json.loads(row[0])
                return PhysicalObject.from_dict(object_data)
            
            return None
    
    def get_objects_by_type(self, object_type: str) -> List[PhysicalObject]:
        """Get all objects of a specific type."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT object_data FROM physical_objects
                WHERE json_extract(object_data, '$.object_type') = ?
                ORDER BY timestamp DESC
                """,
                (object_type,)
            )
            
            objects = []
            for row in cursor.fetchall():
                object_data = json.loads(row[0])
                objects.append(PhysicalObject.from_dict(object_data))
            
            return objects
    
    def get_all_objects(self, limit: int = 100) -> List[PhysicalObject]:
        """Get all objects."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT object_data FROM physical_objects ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )
            
            objects = []
            for row in cursor.fetchall():
                object_data = json.loads(row[0])
                objects.append(PhysicalObject.from_dict(object_data))
            
            return objects
    
    def record_sensor_reading(
        self,
        sensor_type: SensorType,
        data: Dict[str, Any],
        confidence: float = 1.0
    ) -> SensorReading:
        """
        Record a sensor reading.
        
        Args:
            sensor_type: Type of sensor
            data: Sensor data
            confidence: Confidence in the reading (0-1)
        
        Returns:
            SensorReading object
        """
        reading = SensorReading(
            sensor_type=sensor_type,
            data=data,
            confidence=confidence
        )
        
        self._save_reading(reading)
        
        app_logger.info(f"Recorded {sensor_type.value} sensor reading (confidence: {confidence:.2f})")
        
        return reading
    
    def get_recent_readings(
        self,
        sensor_type: Optional[SensorType] = None,
        limit: int = 20
    ) -> List[SensorReading]:
        """
        Get recent sensor readings.
        
        Args:
            sensor_type: Filter by sensor type (optional)
            limit: Maximum number of readings to return
        
        Returns:
            List of SensorReading objects (most recent first)
        """
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT reading_data FROM sensor_readings"
            params = []
            
            if sensor_type:
                query += " WHERE sensor_type = ?"
                params.append(sensor_type.value)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            
            readings = []
            for row in cursor.fetchall():
                reading_data = json.loads(row[0])
                readings.append(SensorReading.from_dict(reading_data))
            
            return readings
    
    def plan_action(
        self,
        action_type: ActionType,
        target_object_id: Optional[str] = None,
        end_position: Vector3D = None,
        parameters: Dict[str, Any] = None
    ) -> MotorAction:
        """
        Plan a motor action.
        
        Args:
            action_type: Type of action
            target_object_id: Target object (optional)
            end_position: End position for the action
            parameters: Action parameters
        
        Returns:
            MotorAction object (planned)
        """
        start_position = self.agent_position
        
        action = MotorAction(
            action_type=action_type,
            target_object_id=target_object_id,
            start_position=start_position,
            end_position=end_position or Vector3D(),
            parameters=parameters or {}
        )
        
        app_logger.info(
            f"Planned {action_type.value} action"
            f"{f' on object {target_object_id}' if target_object_id else ''}"
        )
        
        return action
    
    def execute_action(self, action: MotorAction) -> MotorAction:
        """
        Execute a motor action.
        
        Args:
            action: Action to execute
        
        Returns:
            Updated MotorAction with execution results
        """
        import time
        start_time = time.time()
        
        # Simulate action execution
        # In a real system, this would interface with actuators
        errors = []
        success = True
        
        # Check if target object exists and is movable
        if action.target_object_id:
            obj = self.get_object(action.target_object_id)
            if not obj:
                errors.append(f"Target object {action.target_object_id} not found")
                success = False
            elif not obj.movable and action.action_type in [
                ActionType.MOVE, ActionType.PUSH, ActionType.PULL, ActionType.LIFT
            ]:
                errors.append(f"Object {obj.name} is not movable")
                success = False
        
        # Update agent position for movement actions
        if success and action.action_type == ActionType.MOVE:
            self.agent_position = action.end_position
        
        # Update object position for object manipulation
        if success and action.target_object_id and action.action_type in [
            ActionType.MOVE, ActionType.PUSH, ActionType.PULL, ActionType.PLACE
        ]:
            self.update_object_position(action.target_object_id, action.end_position)
        
        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000
        action.duration_ms = duration_ms
        action.success = success
        action.errors = errors
        action.timestamp = _now()
        
        # Save action
        self._save_action(action)
        
        app_logger.info(
            f"Executed {action.action_type.value} action: "
            f"success={success}, duration={duration_ms:.1f}ms"
        )
        
        return action
    
    def get_recent_actions(
        self,
        action_type: Optional[ActionType] = None,
        limit: int = 20
    ) -> List[MotorAction]:
        """
        Get recent motor actions.
        
        Args:
            action_type: Filter by action type (optional)
            limit: Maximum number of actions to return
        
        Returns:
            List of MotorAction objects (most recent first)
        """
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT action_data FROM motor_actions"
            params = []
            
            if action_type:
                query += " WHERE action_type = ?"
                params.append(action_type.value)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            
            actions = []
            for row in cursor.fetchall():
                action_data = json.loads(row[0])
                actions.append(MotorAction.from_dict(action_data))
            
            return actions
    
    def compute_spatial_relationship(
        self,
        object1_id: str,
        object2_id: str
    ) -> Optional[SpatialRelationship]:
        """
        Compute the spatial relationship between two objects.
        
        Args:
            object1_id: First object ID
            object2_id: Second object ID
        
        Returns:
            SpatialRelationship or None if objects not found
        """
        obj1 = self.get_object(object1_id)
        obj2 = self.get_object(object2_id)
        
        if not obj1 or not obj2:
            app_logger.error("One or both objects not found")
            return None
        
        # Calculate distance
        distance = obj1.position.distance_to(obj2.position)
        
        # Determine relationship type based on relative positions
        delta = obj2.position - obj1.position
        
        # Primary relationship based on largest component
        if abs(delta.z) > abs(delta.x) and abs(delta.z) > abs(delta.y):
            if delta.z > 0:
                relation_type = SpatialRelation.ABOVE
            else:
                relation_type = SpatialRelation.BELOW
        elif abs(delta.x) > abs(delta.y):
            if delta.x > 0:
                relation_type = SpatialRelation.RIGHT
            else:
                relation_type = SpatialRelation.LEFT
        else:
            if delta.y > 0:
                relation_type = SpatialRelation.FRONT
            else:
                relation_type = SpatialRelation.BACK
        
        # Override with NEAR if very close
        if distance < 0.1:  # 10cm threshold
            relation_type = SpatialRelation.NEAR
        
        relationship = SpatialRelationship(
            object1_id=object1_id,
            object2_id=object2_id,
            relation_type=relation_type,
            distance=distance,
            confidence=1.0
        )
        
        self._save_relationship(relationship)
        
        app_logger.info(
            f"Computed spatial relationship: {obj1.name} is {relation_type.value} {obj2.name} "
            f"(distance: {distance:.2f}m)"
        )
        
        return relationship
    
    def get_relationships_for_object(
        self,
        object_id: str,
        limit: int = 20
    ) -> List[SpatialRelationship]:
        """
        Get all spatial relationships involving an object.
        
        Args:
            object_id: Object ID
            limit: Maximum number of relationships to return
        
        Returns:
            List of SpatialRelationship objects
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT relationship_data FROM spatial_relationships
                WHERE object1_id = ? OR object2_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (object_id, object_id, limit)
            )
            
            relationships = []
            for row in cursor.fetchall():
                relationship_data = json.loads(row[0])
                relationships.append(SpatialRelationship.from_dict(relationship_data))
            
            return relationships
    
    def get_embodied_summary(self) -> Dict[str, Any]:
        """
        Get summary of embodied cognition activity.
        
        Returns:
            Dictionary with embodied metrics
        """
        with sqlite3.connect(self.db_path) as conn:
            # Count objects
            cursor = conn.execute("SELECT COUNT(*) FROM physical_objects")
            object_count = cursor.fetchone()[0]
            
            # Count objects by type
            cursor = conn.execute("""
                SELECT json_extract(object_data, '$.object_type'), COUNT(*)
                FROM physical_objects
                GROUP BY json_extract(object_data, '$.object_type')
            """)
            objects_by_type = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Count sensor readings
            cursor = conn.execute("SELECT COUNT(*) FROM sensor_readings")
            reading_count = cursor.fetchone()[0]
            
            # Count readings by type
            cursor = conn.execute("""
                SELECT sensor_type, COUNT(*)
                FROM sensor_readings
                GROUP BY sensor_type
            """)
            readings_by_type = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Count actions
            cursor = conn.execute("SELECT COUNT(*) FROM motor_actions")
            action_count = cursor.fetchone()[0]
            
            # Count actions by type
            cursor = conn.execute("""
                SELECT action_type, COUNT(*)
                FROM motor_actions
                GROUP BY action_type
            """)
            actions_by_type = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Count successful actions
            cursor = conn.execute("""
                SELECT COUNT(*) FROM motor_actions
                WHERE json_extract(action_data, '$.success') = 1
            """)
            successful_actions = cursor.fetchone()[0]
            
            # Count relationships
            cursor = conn.execute("SELECT COUNT(*) FROM spatial_relationships")
            relationship_count = cursor.fetchone()[0]
            
            return {
                "total_objects": object_count,
                "objects_by_type": objects_by_type,
                "total_sensor_readings": reading_count,
                "readings_by_type": readings_by_type,
                "total_actions": action_count,
                "actions_by_type": actions_by_type,
                "successful_actions": successful_actions,
                "success_rate": successful_actions / action_count if action_count > 0 else 0.0,
                "total_relationships": relationship_count,
                "agent_position": self.agent_position.to_dict(),
                "agent_orientation": self.agent_orientation.to_dict()
            }
    
    def _save_object(self, obj: PhysicalObject) -> None:
        """Save physical object to database."""
        object_data = json.dumps(obj.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO physical_objects
                (object_id, name, object_data, timestamp)
                VALUES (?, ?, ?, ?)
            """, (
                obj.object_id,
                obj.name,
                object_data,
                obj.timestamp
            ))
            conn.commit()
    
    def _save_reading(self, reading: SensorReading) -> None:
        """Save sensor reading to database."""
        reading_data = json.dumps(reading.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO sensor_readings
                (reading_id, sensor_type, reading_data, timestamp)
                VALUES (?, ?, ?, ?)
            """, (
                reading.reading_id,
                reading.sensor_type.value,
                reading_data,
                reading.timestamp
            ))
            conn.commit()
    
    def _save_action(self, action: MotorAction) -> None:
        """Save motor action to database."""
        action_data = json.dumps(action.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO motor_actions
                (action_id, action_type, action_data, timestamp)
                VALUES (?, ?, ?, ?)
            """, (
                action.action_id,
                action.action_type.value,
                action_data,
                action.timestamp
            ))
            conn.commit()
    
    def _save_relationship(self, relationship: SpatialRelationship) -> None:
        """Save spatial relationship to database."""
        relationship_data = json.dumps(relationship.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO spatial_relationships
                (relationship_id, object1_id, object2_id, relationship_data, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (
                relationship.relationship_id,
                relationship.object1_id,
                relationship.object2_id,
                relationship_data,
                relationship.timestamp
            ))
            conn.commit()
