"""Observation-router file-question queries must be FILENAMES, not clauses.

Recon for the F7 marker fix (owner diagnostics, 2026-09-01) found a live
user-facing bug on the way: 'Find files matching arena_diag_marker_x.txt,
then tell me how many you found.' planned a search_files observation
whose QUERY was the whole clause — 'find files matching
arena_diag_marker_x.txt' — because the ext-token extraction spans spaces
and swallowed the request verbs. search_files matches filename
SUBSTRINGS: no filename contains the request phrase, so the search can
NEVER match — every 'find files matching X.ext' question answered 'no
files found' while the file existed. (The P0 #16 lesson — 'the whole user
sentence can never match a filename' — applied to the router's ext-token
path.)

Contract: the planned query is the filename, with request-verb lead
noise stripped. Shorter queries can only match MORE files (substring
semantics), never miss; a name whose leading word is not request noise
('report.pdf') survives intact.
"""

from app.cognition.observation_router import plan_observation


def _query(text):
    plan = plan_observation(text)
    return plan.payload.get("query") if plan else None


def test_find_files_matching_ext_searches_the_filename():
    assert _query("Find files matching arena_diag_marker_abc12345.txt, "
                  "then tell me how many you found.") == \
        "arena_diag_marker_abc12345.txt"


def test_where_is_my_archive_searches_the_filename():
    assert _query("where is my backup.zip") == "backup.zip"


def test_multiword_filename_is_preserved():
    assert _query("do i have vacation photo.jpg on my pc") == "vacation photo.jpg"


def test_name_that_is_not_request_noise_survives_intact():
    # 'report' is not request noise — the name itself must survive.
    assert _query("where is report.pdf") == "report.pdf"


def test_search_verb_lead_is_stripped():
    assert _query("search for invoices 2026.xlsx") == "invoices 2026.xlsx"
