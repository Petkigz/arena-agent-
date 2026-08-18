from app.cognition.goal_interpreter import SemanticGoalInterpreter


def test_desktop_os_query_assigns_domain_specific_semantic_attributes():
    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")
    assert goal_rep.target_domain == "desktop_os"
    assert "user_session_active" in goal_rep.constraints
    assert "application installed on host PC" in goal_rep.assumptions
    assert "os_gui_running" in goal_rep.preconditions
    assert "app_process_running = true" in goal_rep.success_conditions
    assert "process_crashed = true" in goal_rep.failure_conditions
    assert "unwanted_process_execution" in goal_rep.risk_factors


def test_filesystem_query_assigns_domain_specific_semantic_attributes():
    goal_rep = SemanticGoalInterpreter.interpret_goal("Find document contract.pdf")
    assert goal_rep.target_domain == "filesystem"
    assert "workspace_boundary_enforced" in goal_rep.constraints
    assert "file resides in local storage" in goal_rep.assumptions
    assert "storage_mounted" in goal_rep.preconditions
    assert "file_path_identified = true" in goal_rep.success_conditions
    assert "file_not_found = true" in goal_rep.failure_conditions
    assert "unintended_file_modification" in goal_rep.risk_factors


def test_web_research_query_assigns_domain_specific_semantic_attributes():
    goal_rep = SemanticGoalInterpreter.interpret_goal("Search web for Qwen2.5 benchmarks")
    assert goal_rep.target_domain == "web_research"
    assert "no_paid_apis" in goal_rep.constraints
    assert "local_wifi_or_internet_connected" in goal_rep.assumptions
    assert "network_available" in goal_rep.preconditions
    assert "search_results_retrieved = true" in goal_rep.success_conditions
    assert "network_error = true" in goal_rep.failure_conditions
