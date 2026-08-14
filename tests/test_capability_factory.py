import pytest
import os
from app.cognition.capability_factory import CapabilityFactory

def test_capability_factory():
    res = CapabilityFactory.synthesize_capability(
        capability_name="System Log Analyzer",
        description="Parses system logs and filters warnings"
    )
    assert res["success"] is True
    assert os.path.exists(res["file_path"])
