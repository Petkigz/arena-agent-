"""Config env naming — one convention, two spellings (audit 2026-09-09).

The settings loader declared ``env_prefix="LPA_"`` while the docs, the
comments, and half the codebase's kill switches (read via
``os.environ`` directly) used the bare names — so owner-facing
instructions like ``ARENA_PARKED_RECHECK=0`` were silently ignored by
the loader. Both spellings are now loaded for ARENA_* switches and the
model/autonomy knobs; ``LPA_`` wins when both are set; generic fields
(``DEBUG``, ``DB_PATH`` …) stay prefixed-only so an unrelated machine
env var can never hijack them.
"""

from app.config import Settings


def test_bare_arena_switch_is_loaded(monkeypatch):
    monkeypatch.setenv("ARENA_PARKED_RECHECK", "0")
    monkeypatch.delenv("LPA_ARENA_PARKED_RECHECK", raising=False)
    assert Settings().ARENA_PARKED_RECHECK == "0"


def test_prefixed_name_wins_when_both_set(monkeypatch):
    monkeypatch.setenv("ARENA_PARKED_RECHECK", "0")
    monkeypatch.setenv("LPA_ARENA_PARKED_RECHECK", "1")
    assert Settings().ARENA_PARKED_RECHECK == "1"


def test_bare_model_and_autonomy_names_are_loaded(monkeypatch):
    monkeypatch.setenv("MAIN_MODEL", "auto")
    monkeypatch.setenv("FAST_MODEL", "auto")
    monkeypatch.setenv("AUTONOMY_MODE", "off")
    for prefixed in ("LPA_MAIN_MODEL", "LPA_FAST_MODEL", "LPA_AUTONOMY_MODE"):
        monkeypatch.delenv(prefixed, raising=False)
    s = Settings()
    assert s.MAIN_MODEL == "auto"
    assert s.FAST_MODEL == "auto"
    assert s.AUTONOMY_MODE == "off"


def test_prefixed_model_names_still_loaded(monkeypatch):
    monkeypatch.setenv("LPA_MAIN_MODEL", "auto")
    monkeypatch.delenv("MAIN_MODEL", raising=False)
    assert Settings().MAIN_MODEL == "auto"


def test_code_model_knobs_accept_bare_names(monkeypatch):
    monkeypatch.setenv("CODE_MODEL_AUTOSWAP", "0")
    monkeypatch.delenv("LPA_CODE_MODEL_AUTOSWAP", raising=False)
    assert Settings().CODE_MODEL_AUTOSWAP == "0"


def test_generic_fields_stay_prefixed_only(monkeypatch):
    # A stray DEBUG/APP_NAME in the machine env must NOT hijack settings:
    # only the allowlisted knob families accept bare names.
    monkeypatch.setenv("DEBUG", "False")
    monkeypatch.setenv("APP_NAME", "Hijacked")
    monkeypatch.delenv("LPA_DEBUG", raising=False)
    monkeypatch.delenv("LPA_APP_NAME", raising=False)
    s = Settings()
    assert s.DEBUG is True
    assert s.APP_NAME == "Local Personal Assistant"
