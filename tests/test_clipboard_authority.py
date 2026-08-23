import sys
from types import SimpleNamespace
from app.tools.security_canary import SecurityCanaryTrap

def test_inspection_never_clears_sensitive_clipboard(monkeypatch):
 state={'value':'A1b2C3d4E5f6G7h8I9j0K!@#$%^&*'}
 fake=SimpleNamespace(paste=lambda:state['value'],copy=lambda value:state.update(value=value))
 monkeypatch.setitem(sys.modules,'pyperclip',fake)
 r=SecurityCanaryTrap.inspect_clipboard_entropy()
 assert r['success'] is True and r['sensitive_detected'] is True
 assert r['clipboard_cleared'] is False and r['requires_approval'] is True
 assert state['value']

def test_separate_clear_action_verifies_empty_and_has_no_fake_rollback(monkeypatch):
 state={'value':'A1b2C3d4E5f6G7h8I9j0K!@#$%^&*'}
 fake=SimpleNamespace(paste=lambda:state['value'],copy=lambda value:state.update(value=value))
 monkeypatch.setitem(sys.modules,'pyperclip',fake)
 r=SecurityCanaryTrap.clear_sensitive_clipboard()
 assert r['success'] is True and r['environment_verified'] is True
 assert state['value']=='' and r['rollback_supported'] is False
