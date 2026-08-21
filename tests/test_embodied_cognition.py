"""
Tests for Phase 20: Embodied Cognition
"""

import pytest
import tempfile
import os
from app.cognition.embodied_cognition import (
    EmbodiedCognitionEngine,
    PhysicalObject,
    SensorReading,
    MotorAction,
    SpatialRelationship,
    Vector3D,
    SpatialRelation,
    ActionType,
    SensorType
)


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing (isolated via tmp_path)."""
    yield str(tmp_path / "test.db")


@pytest.fixture
def engine(temp_db):
    """Create an embodied cognition engine with temp database."""
    return EmbodiedCognitionEngine(db_path=temp_db)


class TestEmbodiedCognition:
    """Test suite for embodied cognition functionality."""
    
    def test_vector3d_operations(self):
        """Test Vector3D operations."""
        v1 = Vector3D(1.0, 2.0, 3.0)
        v2 = Vector3D(4.0, 5.0, 6.0)
        
        # Test addition
        v3 = v1 + v2
        assert v3.x == 5.0
        assert v3.y == 7.0
        assert v3.z == 9.0
        
        # Test subtraction
        v4 = v2 - v1
        assert v4.x == 3.0
        assert v4.y == 3.0
        assert v4.z == 3.0
        
        # Test magnitude
        v5 = Vector3D(3.0, 4.0, 0.0)
        assert abs(v5.magnitude() - 5.0) < 0.001
        
        # Test distance
        v6 = Vector3D(0.0, 0.0, 0.0)
        v7 = Vector3D(3.0, 4.0, 0.0)
        assert abs(v6.distance_to(v7) - 5.0) < 0.001
        
        # Test normalize
        v8 = Vector3D(3.0, 4.0, 0.0)
        v9 = v8.normalize()
        assert abs(v9.magnitude() - 1.0) < 0.001
    
    def test_add_object(self, engine):
        """Test adding a physical object."""
        obj = engine.add_object(
            name="Coffee Cup",
            object_type="cup",
            position=Vector3D(1.0, 2.0, 0.5),
            orientation=Vector3D(0.0, 0.0, 0.0),
            dimensions=Vector3D(0.1, 0.15, 0.1),
            mass=0.3,
            color="white",
            material="ceramic",
            graspable=True,
            movable=True,
            properties={"temperature": "hot", "contents": "coffee"}
        )
        
        assert obj.object_id is not None
        assert obj.name == "Coffee Cup"
        assert obj.object_type == "cup"
        assert obj.position.x == 1.0
        assert obj.position.y == 2.0
        assert obj.position.z == 0.5
        assert obj.mass == 0.3
        assert obj.color == "white"
        assert obj.material == "ceramic"
        assert obj.graspable is True
        assert obj.movable is True
        assert obj.properties["temperature"] == "hot"
    
    def test_update_object_position(self, engine):
        """Test updating object position."""
        obj = engine.add_object(
            name="Book",
            object_type="book",
            position=Vector3D(0.0, 0.0, 0.0),
            movable=True
        )
        
        # Update position
        new_pos = Vector3D(1.0, 1.0, 0.5)
        updated = engine.update_object_position(obj.object_id, new_pos)
        
        assert updated is not None
        assert updated.position.x == 1.0
        assert updated.position.y == 1.0
        assert updated.position.z == 0.5
        
        # Update position and orientation
        new_pos2 = Vector3D(2.0, 2.0, 1.0)
        new_orient = Vector3D(0.0, 0.0, 90.0)
        updated2 = engine.update_object_position(obj.object_id, new_pos2, new_orient)
        
        assert updated2.position.x == 2.0
        assert updated2.orientation.z == 90.0
    
    def test_update_nonexistent_object(self, engine):
        """Test updating a nonexistent object."""
        result = engine.update_object_position("nonexistent_id", Vector3D(1.0, 1.0, 1.0))
        assert result is None
    
    def test_get_object(self, engine):
        """Test getting an object by ID."""
        obj = engine.add_object(
            name="Chair",
            object_type="furniture",
            position=Vector3D(3.0, 4.0, 0.0)
        )
        
        retrieved = engine.get_object(obj.object_id)
        assert retrieved is not None
        assert retrieved.object_id == obj.object_id
        assert retrieved.name == "Chair"
    
    def test_get_nonexistent_object(self, engine):
        """Test getting a nonexistent object."""
        result = engine.get_object("nonexistent_id")
        assert result is None
    
    def test_get_objects_by_type(self, engine):
        """Test getting objects by type."""
        # Add multiple objects
        engine.add_object(name="Cup 1", object_type="cup", position=Vector3D(0, 0, 0))
        engine.add_object(name="Cup 2", object_type="cup", position=Vector3D(1, 0, 0))
        engine.add_object(name="Book 1", object_type="book", position=Vector3D(2, 0, 0))
        
        # Get cups
        cups = engine.get_objects_by_type("cup")
        assert len(cups) == 2
        assert all(obj.object_type == "cup" for obj in cups)
        
        # Get books
        books = engine.get_objects_by_type("book")
        assert len(books) == 1
        assert books[0].object_type == "book"
        
        # Get nonexistent type
        empty = engine.get_objects_by_type("nonexistent")
        assert len(empty) == 0
    
    def test_get_all_objects(self, engine):
        """Test getting all objects."""
        # Add objects
        engine.add_object(name="Obj 1", object_type="type1", position=Vector3D(0, 0, 0))
        engine.add_object(name="Obj 2", object_type="type2", position=Vector3D(1, 0, 0))
        engine.add_object(name="Obj 3", object_type="type3", position=Vector3D(2, 0, 0))
        
        # Get all
        all_objects = engine.get_all_objects()
        assert len(all_objects) == 3
        
        # Get with limit
        limited = engine.get_all_objects(limit=2)
        assert len(limited) == 2
    
    def test_record_sensor_reading(self, engine):
        """Test recording sensor readings."""
        reading = engine.record_sensor_reading(
            sensor_type=SensorType.VISUAL,
            data={"image": "base64_encoded_image", "objects_detected": 5},
            confidence=0.95
        )
        
        assert reading.reading_id is not None
        assert reading.sensor_type == SensorType.VISUAL
        assert reading.data["objects_detected"] == 5
        assert reading.confidence == 0.95
    
    def test_get_recent_readings(self, engine):
        """Test getting recent sensor readings."""
        # Add readings
        for i in range(5):
            engine.record_sensor_reading(
                sensor_type=SensorType.VISUAL if i % 2 == 0 else SensorType.DEPTH,
                data={"frame": i},
                confidence=0.9
            )
        
        # Get all recent
        recent = engine.get_recent_readings(limit=10)
        assert len(recent) == 5
        
        # Get with limit
        limited = engine.get_recent_readings(limit=3)
        assert len(limited) == 3
        
        # Filter by type
        visual = engine.get_recent_readings(sensor_type=SensorType.VISUAL, limit=10)
        assert len(visual) == 3
        assert all(r.sensor_type == SensorType.VISUAL for r in visual)
        
        depth = engine.get_recent_readings(sensor_type=SensorType.DEPTH, limit=10)
        assert len(depth) == 2
        assert all(r.sensor_type == SensorType.DEPTH for r in depth)
    
    def test_plan_action(self, engine):
        """Test planning motor actions."""
        # Plan movement
        action = engine.plan_action(
            action_type=ActionType.MOVE,
            end_position=Vector3D(5.0, 5.0, 0.0),
            parameters={"speed": 1.5}
        )
        
        assert action.action_id is not None
        assert action.action_type == ActionType.MOVE
        assert action.end_position.x == 5.0
        assert action.parameters["speed"] == 1.5
        assert action.start_position.x == 0.0  # Agent starts at origin
        
        # Plan grasp
        obj = engine.add_object(name="Cup", object_type="cup", position=Vector3D(1, 1, 0))
        grasp_action = engine.plan_action(
            action_type=ActionType.GRASP,
            target_object_id=obj.object_id
        )
        
        assert grasp_action.action_type == ActionType.GRASP
        assert grasp_action.target_object_id == obj.object_id
    
    def test_execute_action_movement(self, engine):
        """Test executing movement action."""
        action = engine.plan_action(
            action_type=ActionType.MOVE,
            end_position=Vector3D(3.0, 4.0, 0.0)
        )
        
        executed = engine.execute_action(action)
        
        assert executed.success is True
        assert executed.duration_ms >= 0
        assert len(executed.errors) == 0
        assert engine.agent_position.x == 3.0
        assert engine.agent_position.y == 4.0
    
    def test_execute_action_object_manipulation(self, engine):
        """Test executing object manipulation action."""
        obj = engine.add_object(
            name="Box",
            object_type="box",
            position=Vector3D(1.0, 1.0, 0.0),
            movable=True
        )
        
        action = engine.plan_action(
            action_type=ActionType.MOVE,
            target_object_id=obj.object_id,
            end_position=Vector3D(2.0, 2.0, 0.0)
        )
        
        executed = engine.execute_action(action)
        
        assert executed.success is True
        
        # Check object was moved
        updated_obj = engine.get_object(obj.object_id)
        assert updated_obj.position.x == 2.0
        assert updated_obj.position.y == 2.0
    
    def test_execute_action_immovable_object(self, engine):
        """Test executing action on immovable object."""
        obj = engine.add_object(
            name="Table",
            object_type="table",
            position=Vector3D(0.0, 0.0, 0.0),
            movable=False
        )
        
        action = engine.plan_action(
            action_type=ActionType.MOVE,
            target_object_id=obj.object_id,
            end_position=Vector3D(1.0, 1.0, 0.0)
        )
        
        executed = engine.execute_action(action)
        
        assert executed.success is False
        assert len(executed.errors) > 0
        assert "not movable" in executed.errors[0].lower()
    
    def test_execute_action_nonexistent_object(self, engine):
        """Test executing action on nonexistent object."""
        action = engine.plan_action(
            action_type=ActionType.GRASP,
            target_object_id="nonexistent_id"
        )
        
        executed = engine.execute_action(action)
        
        assert executed.success is False
        assert len(executed.errors) > 0
        assert "not found" in executed.errors[0].lower()
    
    def test_get_recent_actions(self, engine):
        """Test getting recent motor actions."""
        # Add actions
        for i in range(5):
            action = engine.plan_action(
                action_type=ActionType.MOVE,
                end_position=Vector3D(i, i, 0)
            )
            engine.execute_action(action)
        
        # Get all recent
        recent = engine.get_recent_actions(limit=10)
        assert len(recent) == 5
        
        # Get with limit
        limited = engine.get_recent_actions(limit=3)
        assert len(limited) == 3
        
        # Filter by type
        move_actions = engine.get_recent_actions(action_type=ActionType.MOVE, limit=10)
        assert len(move_actions) == 5
        assert all(a.action_type == ActionType.MOVE for a in move_actions)
    
    def test_compute_spatial_relationship(self, engine):
        """Test computing spatial relationships."""
        obj1 = engine.add_object(
            name="Cup",
            object_type="cup",
            position=Vector3D(0.0, 0.0, 0.0)
        )
        
        obj2 = engine.add_object(
            name="Book",
            object_type="book",
            position=Vector3D(0.0, 0.0, 1.0)  # Above cup
        )
        
        relationship = engine.compute_spatial_relationship(obj1.object_id, obj2.object_id)
        
        assert relationship is not None
        assert relationship.object1_id == obj1.object_id
        assert relationship.object2_id == obj2.object_id
        assert relationship.relation_type == SpatialRelation.ABOVE
        assert abs(relationship.distance - 1.0) < 0.001
        assert relationship.confidence == 1.0
    
    def test_compute_spatial_relationship_nonexistent(self, engine):
        """Test computing spatial relationship with nonexistent object."""
        obj = engine.add_object(name="Cup", object_type="cup", position=Vector3D(0, 0, 0))
        
        result = engine.compute_spatial_relationship(obj.object_id, "nonexistent_id")
        assert result is None
    
    def test_compute_different_spatial_relationships(self, engine):
        """Test computing different types of spatial relationships."""
        center = engine.add_object(
            name="Center",
            object_type="marker",
            position=Vector3D(0.0, 0.0, 0.0)
        )
        
        # Test ABOVE
        above = engine.add_object(name="Above", object_type="marker", position=Vector3D(0.0, 0.0, 1.0))
        rel_above = engine.compute_spatial_relationship(center.object_id, above.object_id)
        assert rel_above.relation_type == SpatialRelation.ABOVE
        
        # Test BELOW
        below = engine.add_object(name="Below", object_type="marker", position=Vector3D(0.0, 0.0, -1.0))
        rel_below = engine.compute_spatial_relationship(center.object_id, below.object_id)
        assert rel_below.relation_type == SpatialRelation.BELOW
        
        # Test RIGHT
        right = engine.add_object(name="Right", object_type="marker", position=Vector3D(1.0, 0.0, 0.0))
        rel_right = engine.compute_spatial_relationship(center.object_id, right.object_id)
        assert rel_right.relation_type == SpatialRelation.RIGHT
        
        # Test LEFT
        left = engine.add_object(name="Left", object_type="marker", position=Vector3D(-1.0, 0.0, 0.0))
        rel_left = engine.compute_spatial_relationship(center.object_id, left.object_id)
        assert rel_left.relation_type == SpatialRelation.LEFT
        
        # Test NEAR (very close)
        near = engine.add_object(name="Near", object_type="marker", position=Vector3D(0.05, 0.0, 0.0))
        rel_near = engine.compute_spatial_relationship(center.object_id, near.object_id)
        assert rel_near.relation_type == SpatialRelation.NEAR
    
    def test_get_relationships_for_object(self, engine):
        """Test getting relationships for an object."""
        obj1 = engine.add_object(name="Obj1", object_type="type", position=Vector3D(0, 0, 0))
        obj2 = engine.add_object(name="Obj2", object_type="type", position=Vector3D(1, 0, 0))
        obj3 = engine.add_object(name="Obj3", object_type="type", position=Vector3D(2, 0, 0))
        
        # Compute relationships
        engine.compute_spatial_relationship(obj1.object_id, obj2.object_id)
        engine.compute_spatial_relationship(obj1.object_id, obj3.object_id)
        engine.compute_spatial_relationship(obj2.object_id, obj3.object_id)
        
        # Get relationships for obj1
        rels1 = engine.get_relationships_for_object(obj1.object_id)
        assert len(rels1) == 2
        
        # Get relationships for obj2
        rels2 = engine.get_relationships_for_object(obj2.object_id)
        assert len(rels2) == 2
        
        # Get relationships for obj3
        rels3 = engine.get_relationships_for_object(obj3.object_id)
        assert len(rels3) == 2
    
    def test_get_embodied_summary(self, engine):
        """Test getting embodied cognition summary."""
        # Add objects
        engine.add_object(name="Cup", object_type="cup", position=Vector3D(0, 0, 0))
        engine.add_object(name="Book", object_type="book", position=Vector3D(1, 0, 0))
        
        # Add sensor readings
        engine.record_sensor_reading(SensorType.VISUAL, {"frame": 1})
        engine.record_sensor_reading(SensorType.DEPTH, {"depth_map": "data"})
        
        # Add actions
        action = engine.plan_action(ActionType.MOVE, end_position=Vector3D(2, 2, 0))
        engine.execute_action(action)
        
        # Get summary
        summary = engine.get_embodied_summary()
        
        assert summary["total_objects"] == 2
        assert summary["objects_by_type"]["cup"] == 1
        assert summary["objects_by_type"]["book"] == 1
        assert summary["total_sensor_readings"] == 2
        assert summary["readings_by_type"]["visual"] == 1
        assert summary["readings_by_type"]["depth"] == 1
        assert summary["total_actions"] == 1
        assert summary["actions_by_type"]["move"] == 1
        assert summary["successful_actions"] == 1
        assert summary["success_rate"] == 1.0
        assert summary["total_relationships"] == 0
    
    def test_physical_object_serialization(self):
        """Test physical object serialization."""
        obj = PhysicalObject(
            object_id="obj123",
            name="Test Object",
            object_type="test",
            position=Vector3D(1.0, 2.0, 3.0),
            orientation=Vector3D(0.0, 90.0, 0.0),
            dimensions=Vector3D(0.5, 0.5, 0.5),
            mass=2.5,
            color="red",
            material="metal",
            graspable=True,
            movable=True,
            properties={"temperature": "cold"}
        )
        
        # Serialize
        obj_dict = obj.to_dict()
        
        # Deserialize
        restored = PhysicalObject.from_dict(obj_dict)
        
        assert restored.object_id == obj.object_id
        assert restored.name == obj.name
        assert restored.object_type == obj.object_type
        assert restored.position.x == obj.position.x
        assert restored.position.y == obj.position.y
        assert restored.position.z == obj.position.z
        assert restored.orientation.y == obj.orientation.y
        assert restored.dimensions.x == obj.dimensions.x
        assert restored.mass == obj.mass
        assert restored.color == obj.color
        assert restored.material == obj.material
        assert restored.graspable == obj.graspable
        assert restored.movable == obj.movable
        assert restored.properties == obj.properties
    
    def test_sensor_reading_serialization(self):
        """Test sensor reading serialization."""
        reading = SensorReading(
            reading_id="reading123",
            sensor_type=SensorType.VISUAL,
            data={"image": "base64", "objects": 5},
            confidence=0.92
        )
        
        # Serialize
        reading_dict = reading.to_dict()
        
        # Deserialize
        restored = SensorReading.from_dict(reading_dict)
        
        assert restored.reading_id == reading.reading_id
        assert restored.sensor_type == reading.sensor_type
        assert restored.data == reading.data
        assert restored.confidence == reading.confidence
    
    def test_motor_action_serialization(self):
        """Test motor action serialization."""
        action = MotorAction(
            action_id="action123",
            action_type=ActionType.GRASP,
            target_object_id="obj123",
            start_position=Vector3D(0.0, 0.0, 0.0),
            end_position=Vector3D(1.0, 1.0, 0.5),
            parameters={"grip_force": 5.0},
            duration_ms=1500.0,
            success=True,
            errors=[]
        )
        
        # Serialize
        action_dict = action.to_dict()
        
        # Deserialize
        restored = MotorAction.from_dict(action_dict)
        
        assert restored.action_id == action.action_id
        assert restored.action_type == action.action_type
        assert restored.target_object_id == action.target_object_id
        assert restored.start_position.x == action.start_position.x
        assert restored.end_position.x == action.end_position.x
        assert restored.parameters == action.parameters
        assert restored.duration_ms == action.duration_ms
        assert restored.success == action.success
        assert restored.errors == action.errors
    
    def test_spatial_relationship_serialization(self):
        """Test spatial relationship serialization."""
        relationship = SpatialRelationship(
            relationship_id="rel123",
            object1_id="obj1",
            object2_id="obj2",
            relation_type=SpatialRelation.ABOVE,
            distance=1.5,
            confidence=0.98
        )
        
        # Serialize
        rel_dict = relationship.to_dict()
        
        # Deserialize
        restored = SpatialRelationship.from_dict(rel_dict)
        
        assert restored.relationship_id == relationship.relationship_id
        assert restored.object1_id == relationship.object1_id
        assert restored.object2_id == relationship.object2_id
        assert restored.relation_type == relationship.relation_type
        assert restored.distance == relationship.distance
        assert restored.confidence == relationship.confidence


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
