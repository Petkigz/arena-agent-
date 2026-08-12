import pytest
from app.tools.cybersecurity_brain import CybersecurityBrainTool

def test_cybersecurity_languages_knowledge():
    langs = CybersecurityBrainTool.CYBER_LANGUAGES
    assert "python_security" in langs
    assert "shell_bash" in langs
    assert "powershell_security" in langs
    assert "c_cpp_assembly" in langs
    assert "detection_rules" in langs

def test_natural_security_intent_parsing():
    res = CybersecurityBrainTool.parse_natural_security_intent("Check if local web app is vulnerable to SQL injection", target_scope="127.0.0.1")
    assert res["success"] is True
    assert "security_plan" in res

def test_yara_rule_generation():
    yara = CybersecurityBrainTool.generate_yara_rule("Test_Malware", ["malicious_string_pattern_1", "eval_exploit"], meta_description="Test YARA Rule")
    assert yara["success"] is True
    assert "rule Test_Malware" in yara["yara_code"]
    assert 'malicious_string_pattern_1' in yara["yara_code"]

def test_sigma_rule_generation():
    sigma = CybersecurityBrainTool.generate_sigma_rule("Suspicious PowerShell Execution", "process_creation", {"CommandLine": "*powershell.exe -enc*"})
    assert sigma["success"] is True
    assert "Suspicious PowerShell Execution" in sigma["sigma_yaml"]
