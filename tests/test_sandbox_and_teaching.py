import pytest
import os
from app.tools.disposable_sandbox import DisposableSandbox
from app.tools.skill_teaching_engine import SkillTeachingEngine

def test_disposable_sandbox_lifecycle():
    # 1. Create sandbox
    sb = DisposableSandbox.create_sandbox("Test_Temp_Sandbox")
    assert sb["success"] is True
    sandbox_id = sb["sandbox_id"]
    sandbox_path = sb["sandbox_path"]
    assert os.path.exists(sandbox_path)

    # 2. Run command in sandbox
    run_res = DisposableSandbox.run_in_sandbox(sandbox_id, "echo 'Hello Sandbox World' > test.txt")
    assert run_res["success"] is True
    assert os.path.exists(os.path.join(sandbox_path, "test.txt"))

    # 3. Destroy sandbox
    destroy_res = DisposableSandbox.destroy_sandbox(sandbox_id)
    assert destroy_res["success"] is True
    assert not os.path.exists(sandbox_path)

def test_skill_teaching_engine():
    # 1. Teach custom pentesting skill
    teach_res = SkillTeachingEngine.teach_skill(
        skill_name="Web Reconnaissance Methodology",
        category="cybersecurity_pentesting",
        trigger_keywords=["recon", "subdomain", "enum"],
        instructions="Step 1: Discover subdomains. Step 2: Check active HTTP ports. Step 3: Map web tech stack.",
        sample_commands="echo Scanning {target}...",
        safety_rules="Authorized target scope only."
    )
    assert teach_res["success"] is True

    # 2. List taught skills
    skills = SkillTeachingEngine.list_taught_skills()
    assert len(skills) > 0
    match = next((s for s in skills if s["skill_name"] == "Web Reconnaissance Methodology"), None)
    assert match is not None

    # 3. Execute taught skill
    exec_res = SkillTeachingEngine.execute_taught_skill(
        skill_name="Web Reconnaissance Methodology",
        target_parameter="example.com",
        run_in_sandbox=True
    )
    assert exec_res["success"] is True
    assert exec_res["skill_name"] == "Web Reconnaissance Methodology"
