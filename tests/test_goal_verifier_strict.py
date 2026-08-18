from app.cognition.goal_interpreter import SemanticGoalInterpreter, SemanticGoalRepresentation
from app.cognition.goal_verifier import GoalVerifier
from app.cognition.goal_lifecycle import GoalLifecycleState, GoalTracker


def test_goal_verifier_crashed_app_fails_verification():
    """
    Photoshop example: Action launcher returns an action record,
    but application crashes immediately. Verification MUST fail.
    """
    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")
    assert goal_rep.target_domain == "desktop_os"
    assert "app_process_running = true" in goal_rep.success_conditions

    executed_actions = ["Launched Photoshop executable"]
    reply = "Launched Photoshop, but process crashed immediately with code 1."

    res = GoalVerifier.verify_goal_achievement(goal_rep, executed_actions, reply)

    assert res.verified_success is False
    assert res.final_state == GoalLifecycleState.FAILED
    assert len(res.failed_conditions) > 0


def test_goal_verifier_successful_app_launch_passes_verification():
    """
    Photoshop example: Action launcher succeeds and process is running.
    Verification MUST pass.
    """
    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")

    executed_actions = ["Launched Photoshop executable"]
    reply = "Photoshop process is running active on screen."

    res = GoalVerifier.verify_goal_achievement(goal_rep, executed_actions, reply)

    assert res.verified_success is True
    assert res.final_state == GoalLifecycleState.ACHIEVED
    assert "app_process_running = true" in res.met_conditions


def test_goal_verifier_unrelated_action_execution_fails_verification():
    """
    Action executed (e.g. echo hello) but target success condition is not satisfied.
    Execution alone MUST NOT grant verification success.
    """
    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")

    executed_actions = ["Executed echo hello"]
    reply = "Command output: hello"

    res = GoalVerifier.verify_goal_achievement(goal_rep, executed_actions, reply)

    assert res.verified_success is False
    assert res.final_state == GoalLifecycleState.FAILED


def test_goal_verifier_filesystem_file_not_found_fails():
    """
    File search request where file is not found.
    """
    goal_rep = SemanticGoalInterpreter.interpret_goal("Find document contract.pdf")

    executed_actions = ["Searched directory /home/user"]
    reply = "Error: File contract.pdf not found in workspace."

    res = GoalVerifier.verify_goal_achievement(goal_rep, executed_actions, reply)

    assert res.verified_success is False
    assert res.final_state == GoalLifecycleState.FAILED
