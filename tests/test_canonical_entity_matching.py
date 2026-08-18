from app.cognition.goal_verifier import GoalVerifier


def test_canonical_entity_matching_prevents_substring_collisions():
    """
    P1 Fix Verification:
    Verify that matches_canonical_entity matches exact canonical names and aliases
    while preventing substring collisions (e.g. 'chrome' matching 'chromedriver').
    """
    # Exact canonical match
    assert GoalVerifier.matches_canonical_entity("chrome", "chrome.status") is True
    assert GoalVerifier.matches_canonical_entity("chrome", "chrome.exe") is True
    assert GoalVerifier.matches_canonical_entity("photoshop", "photoshop.status") is True

    # Substring collisions MUST be rejected
    assert GoalVerifier.matches_canonical_entity("chrome", "chromedriver.status") is False
    assert GoalVerifier.matches_canonical_entity("chrome", "chromedriver.exe") is False
    assert GoalVerifier.matches_canonical_entity("photoshop", "photoshop_helper.exe") is False


def test_canonical_entity_matching_supports_explicit_aliases():
    """
    Verify that matches_canonical_entity matches explicit entity aliases if provided in attributes.
    """
    attrs = {"aliases": ["google chrome", "chrome.exe"]}
    assert GoalVerifier.matches_canonical_entity("google chrome", "chrome.status", entity_attributes=attrs) is True
    assert GoalVerifier.matches_canonical_entity("chrome", "chrome.exe", entity_attributes=attrs) is True
