"""Arena distinguishes interfaces, owner devices, and proven control events."""
from app.cognition.embodied_boundary import EmbodiedBoundaryModel


def test_boundary_requires_full_control_evidence(tmp_path):
    model=EmbodiedBoundaryModel(tmp_path/'boundary.db')
    model.register('cursor','actuator','shared',can_write=True,available=True,evidence=['tool:mouse_click'])
    command=model.record_event('cursor','mouse_click',actor='arena',execution_id='e1',authorized=True,observed=False,evidence=['command sent'])
    verified=model.record_event('cursor','mouse_click',actor='arena',execution_id='e2',authorized=True,observed=True,evidence=['pointer position observed'])
    assert command.actor=='unknown'
    assert command.confidence<.5
    assert verified.actor=='arena'
    assert verified.confidence>=.9


def test_owner_and_external_boundaries_remain_distinct(tmp_path):
    model=EmbodiedBoundaryModel(tmp_path/'boundary.db')
    owner=model.record_event('keyboard','typed',actor='owner',evidence=['native input event'])
    external=model.record_event('browser','navigation',actor='external',evidence=['remote redirect'])
    assert owner.actor=='owner'
    assert external.actor=='external'
    assert model.events()[0].actor=='external'


def test_snapshot_denies_biological_embodiment(tmp_path):
    model=EmbodiedBoundaryModel(tmp_path/'boundary.db')
    model.register('camera','sensor','owner_device',can_read=True,available=None,evidence=['availability:not_checked'])
    snapshot=model.snapshot()
    assert snapshot['interfaces'][0]['boundary']=='owner_device'
    assert 'not a biological body' in snapshot['note']
