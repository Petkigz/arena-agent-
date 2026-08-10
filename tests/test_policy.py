from app.policy import PolicyEvaluator

def test_policy_read_observe():
    # Level 0 read action should be autonomous
    allowed, reason, level = PolicyEvaluator.evaluate_action("read_file", {"path": "dummy.txt"})
    assert allowed is True
    assert level == 0

def test_policy_draft():
    # Level 1 draft action inside data folder
    allowed, reason, level = PolicyEvaluator.evaluate_action("write_draft", {"path": "data/draft_cv.md"})
    assert allowed is True
    assert level == 1
    
    # Level 1 draft action outside allowed folder (e.g. system folder)
    allowed, reason, level = PolicyEvaluator.evaluate_action("write_draft", {"path": "/etc/passwd"})
    assert allowed is False
    assert level == 1

def test_policy_sensitive():
    # Level 3 action always needs approval
    allowed, reason, level = PolicyEvaluator.evaluate_action("send_email", {"to": "rec@recruiter.com"})
    assert allowed is False
    assert level == 3

def test_network_scope():
    assert PolicyEvaluator.check_network_scope("localhost") is True
    assert PolicyEvaluator.check_network_scope("127.0.0.1") is True
    assert PolicyEvaluator.check_network_scope("192.168.1.100") is True
    assert PolicyEvaluator.check_network_scope("google.com") is False
