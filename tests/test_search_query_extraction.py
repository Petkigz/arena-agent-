"""Filename-search query extraction from compound requests.

External sandbox audit (2026-09): a two-part request — "Find files matching
goal_verifier, then tell me how many you found." — was fed to search_files
as the query 'matching goal_verifier then tell how many found.'. search_files
matches FILENAME SUBSTRINGS against the whole query string, so this could
never match anything: the search 'found nothing' for a file that existed,
the failure cascaded into a web_search misroute, and the owner got a browser
they never asked for instead of their file.

Two honest extraction rules:
  1. the query serves the SEARCH STEP only — compound requests are cut at
     the first sequencing boundary (', then ...');
  2. instruction/discourse vocabulary (tell/how/many/found/read/summarize/
     check/...) never identifies a file and is stripped, token-exactly.
"""

from app.cognition.goal_interpreter import extract_search_query


def test_two_step_request_yields_the_search_object_only():
    assert extract_search_query(
        "Find files matching goal_verifier, then tell me how many you found."
    ) == "goal_verifier"


def test_four_step_request_yields_the_search_object_only():
    assert extract_search_query(
        "Find files matching goal_verifier, read the first one, "
        "summarize it, then check the tests still pass."
    ) == "goal_verifier"


def test_boundary_without_comma():
    assert extract_search_query(
        "find budget then tell me the total"
    ) == "budget"


def test_single_clause_extraction_unchanged():
    # The pre-existing contract for plain requests must not drift.
    assert extract_search_query("search my files for GoalVerifier") == "GoalVerifier"
    assert extract_search_query("find kaba in my music folder") == "kaba"


def test_same_step_conjunction_is_not_a_boundary():
    # 'and' joins objects of the SAME step — both stay in the query.
    assert extract_search_query("find kaba and kaba2") == "kaba kaba2"


def test_real_filename_content_is_never_stripped():
    # Token-exact stripping: instruction words are removed, but the same
    # letters inside real content words survive.
    assert extract_search_query("find checklist") == "checklist"
    assert extract_search_query("find foundation") == "foundation"
    assert extract_search_query("find the readme") == "readme"


def test_all_instruction_words_fall_back_to_the_raw_text():
    # Degenerate input (every token is discourse): the extractor must not
    # return an empty query — it falls back to the raw text, and the
    # caller's honest 'no files found' is still reachable.
    assert extract_search_query("then tell me how many found") == \
        "then tell me how many found"


def test_the_audited_query_actually_matches_a_real_file():
    """Measurement honesty: verify the extracted query against the REAL
    search — the audit's file (goal_verifier.py) exists in this repo, so
    the cleaned query must find it where the garbled one found nothing."""
    from app.tools.universal_filesystem import UniversalFilesystem

    query = extract_search_query(
        "Find files matching goal_verifier, then tell me how many you found."
    )
    assert query == "goal_verifier"
    matched = UniversalFilesystem.search_filesystem(
        query, root_dir="app/cognition", max_results=10)
    assert any("goal_verifier" in str(m.get("file_name", "")).lower()
               for m in matched), \
        "the cleaned query must find the file the garbled one missed"
