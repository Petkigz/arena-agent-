"""Host-state questions get real observations; questions sync across clients.

Live lesson: 'how many icons do I have on my desktop' was classified
knowledge_query and answered by pure LLM imagination — the agent has eyes
(filesystem, screen, process list) but nothing routed to them. The
observation router deterministically maps host-state questions to Level-0
read-only tools and the ANSWER branch answers from the evidence.
"""
import json
from unittest.mock import patch

from app.cognition.observation_router import plan_observation, render_observation_evidence
from app.tools.universal_filesystem import UniversalFilesystem


def test_host_state_questions_map_to_read_only_plans(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.cognition.observation_router._desktop_directories",
        lambda: [str(tmp_path)])
    plan = plan_observation("how many icons do I have on my desktop?")
    assert plan is not None and plan.action_type == "list_directory"
    assert plan.question_kind == "desktop_contents"
    assert "never" not in plan.evidence_hint  # evidence, not opinion

    assert plan_observation("what's on my screen right now?").action_type == "screen_capture"
    assert plan_observation("what apps are running?").action_type == "list_processes"
    assert plan_observation("which windows are open?").action_type == "list_windows"
    assert plan_observation("what programs do i have installed?").action_type == "list_apps"


def test_plain_chat_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.cognition.observation_router._desktop_directories",
        lambda: [str(tmp_path)])
    assert plan_observation("hi") is None
    assert plan_observation("what is the capital of France?") is None
    assert plan_observation("can you talk?") is None
    assert plan_observation("do you have wisdom?") is None


def test_list_directory_counts_real_entries(tmp_path):
    (tmp_path / "Chrome.lnk").write_text("x")
    (tmp_path / "readme.txt").write_text("x")
    (tmp_path / ".hidden").write_text("x")
    result = UniversalFilesystem.list_directory([{"path": str(tmp_path)}])
    listing = result["listings"][0]
    assert listing["count"] == 2  # hidden excluded
    assert "Chrome.lnk" in listing["entries"] and ".hidden" not in listing["entries"]
    assert result["side_effects"] is False
    missing = UniversalFilesystem.list_directory([{"path": str(tmp_path / "nope")}])
    assert missing["success"] is False and missing["errors"]


def test_evidence_rendering_for_the_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.cognition.observation_router._desktop_directories",
        lambda: [str(tmp_path)])
    evidence = render_observation_evidence(
        {"success": True, "listings": [
            {"directory": r"C:\Users\PETAR\Desktop", "count": 12, "entries": ["a.lnk"]}]},
        plan_observation("how many icons do i have on my desktop"))
    assert "12 total desktop entries" in evidence
    assert "OBSERVED" in evidence


def test_answer_branch_uses_observation_evidence(tmp_path, monkeypatch):
    """The runtime ANSWER branch must execute the plan and inject evidence."""
    from app.cognition.runtime import CognitiveRuntime

    runtime = CognitiveRuntime.get_instance(str(tmp_path / "rt.db"))

    captured = {}

    def fake_manifest():
        def handler(payload):
            captured.update(payload)
            return {"success": True, "listings": [
                {"directory": r"C:\Users\X\Desktop", "count": 7, "entries": ["a", "b"]}]}

        return {"list_directory": {"safety_level": 0, "handler": handler}}

    import app.tools.manifest as manifest_module
    monkeypatch.setattr(manifest_module, "get_tool_manifest", fake_manifest)
    monkeypatch.setattr(
        "app.cognition.observation_router._desktop_directories",
        lambda: [r"C:\Users\X\Desktop"])

    sent_messages = []
    monkeypatch.setattr(
        "app.llm.llm_client.generate_chat_completion",
        lambda messages=None, **kw: sent_messages.append(messages) or {
            "choices": [{"message": {"content": "7 icons"}}],
        })

    result = runtime.process_cognitive_cycle("how many icons do i have on my desktop?")
    assert result["assistant_reply"].startswith("7 icons")
    assert result["epistemic_presentation"]["confidence_label"] in {"Highly confident", "Moderately confident"}
    assert "Epistemic status:" in result["assistant_reply"]
    system_prompt = sent_messages[0][0]["content"]
    assert "OBSERVED HOST EVIDENCE" in system_prompt
    assert "7 total desktop entries" in system_prompt  # from the tool, not imagination


def test_room_message_broadcast_for_cross_client_sync():
    """Questions broadcast to the room so other clients render them."""
    import asyncio
    from unittest.mock import MagicMock
    from backend.message_router import MessageRouter

    sent = []

    async def send(cid, message):
        sent.append((cid, message))

    router = MessageRouter.__new__(MessageRouter)
    router._check_rate_limit = lambda cid: True

    async def fake_cycle(content, **kw):
        return "ok"

    router._call_cognitive_runtime = fake_cycle
    websocket = MagicMock()

    async def call():
        with patch("backend.message_router.ws_manager", SimpleNamespace := type("W", (), {
            "send_to_conversation": staticmethod(send),
            "join_conversation": staticmethod(lambda ws, cid: None),
        })()), \
             patch("backend.message_router.add_to_history"), \
             patch("backend.message_router.get_conversation_history", return_value=[]):
            handler = MessageRouter._handle_user_message.__get__(router)
            return await handler(websocket, {"conversation_id": "c1", "content": "hi"})

    asyncio.run(call())
    room = [m for cid, m in sent if m["type"] == "room_message"]
    assert room and room[0]["content"] == "hi" and room[0]["message_id"]
    # Dedupe key present so clients can avoid double-rendering their own copy.
    assert "message_id" in room[0]


def test_file_enumeration_questions_get_real_searches():
    """Live bug: 'give me a list of all of the songs called london i have'
    fell through to the LLM, which claimed it had no file access while the
    search tool sat unused. Enumeration now routes to evidence."""
    plan = plan_observation("give me a list of all of the songs called london i have")
    assert plan is not None and plan.action_type == "search_files"
    assert plan.question_kind == "file_search"
    assert plan.payload["query"] == "london"
    assert plan.payload["max_results"] == 50  # enumeration, not existence

    assert plan_observation("list all songs called london").question_kind == "file_search"
    assert plan_observation("how many songs called london do i have").question_kind == "file_search"
    assert plan_observation("which songs do i have called london?").payload["query"] == "london"
    assert plan_observation("find all documents called report").payload["query"] == "report"


def test_file_location_questions_get_real_searches():
    plan = plan_observation("where is the song called tema ensingo?")
    assert plan is not None and plan.action_type == "search_files"
    assert plan.question_kind == "file_location"
    assert plan.payload["query"] == "tema ensingo"
    assert plan_observation("where can i find the file called notes").question_kind == "file_location"


def test_pronoun_followup_resolves_subject_from_previous_turn():
    """'where is it located' right after 'do i have a song called kaba on my
    pc' must search for kaba — the live 39-second failed investigation."""
    plan = plan_observation(
        "where is it located",
        recent_user_messages=["do i have a song called tema ensingo on my pc"],
    )
    assert plan is not None and plan.action_type == "search_files"
    assert plan.payload["query"] == "tema ensingo"
    assert plan.question_kind == "file_location"

    # Without file context in the previous turns, pronouns stay unresolved.
    assert plan_observation("where is it located", recent_user_messages=["what is the weather"]) is None
    assert plan_observation("where is it located") is None


def test_non_file_questions_still_left_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.cognition.observation_router._desktop_directories",
        lambda: [str(tmp_path)])
    assert plan_observation("give me a summary of the movie called inception") is None
    assert plan_observation("tell me all about the song called yesterday") is None
    assert plan_observation("where is london located?") is None  # geography, not files
    assert plan_observation("what is the song called in that movie?") is None
    assert plan_observation("show me all the files on my desktop").question_kind == "desktop_contents"
    assert plan_observation("list all my downloads").question_kind == "downloads_folder"


def test_enumeration_evidence_renders_the_full_list():
    plan = plan_observation("list all songs called london")
    assert plan is not None
    results = [
        {"file_name": f"london-{i}.mp3", "file_path": f"C:/Users/x/Music/london-{i}.mp3"}
        for i in range(3)
    ]
    evidence = render_observation_evidence(results, plan)
    assert "3 match(es)" in evidence
    assert "london-0.mp3" in evidence and "london-2.mp3" in evidence
    assert "enumerate" in evidence
    # Empty result is honest evidence of absence.
    empty = render_observation_evidence([], plan)
    assert "NO matches" in empty


def test_broad_file_question_coverage():
    """The bar is deliberately low: any question naming a file subject gets a
    real search, so the owner never sees 'I don't have file access' again."""
    routes = [
        "give me a list of all of the songs called london i have",
        "list all songs called london",
        "how many songs called london do i have",
        "which songs do i have called london?",
        "find all documents called report",
        "where is the song called tema ensingo?",
        "where can i find the file called notes",
        "search my pc for london",
        "find london",
        "look for tema ensingo",
        "locate the file report",
        "do i have london on my pc",
        "any songs called london?",
        "does my computer have a song called london",
        "do you see a song called london",
        "what's london.mp3?",
        "do i have london.mp3",
        "show me everything called london",
        "got a song called kaba?",
    ]
    for q in routes:
        plan = plan_observation(q)
        assert plan is not None and plan.action_type == "search_files", f"missed: {q}"
        assert plan.payload["query"], f"no query for: {q}"
        assert plan.payload["root_dir"], "search must be rooted somewhere"

    # Action/content questions about the same names stay with their pipelines.
    for q in [
        "play the song called london",
        "delete all files called temp",
        "open the document called report",
        "summarize the file called report",
        "what are the lyrics of the song called london",
        "tell me about the song called london",
        "find out why my pc is slow",
        "search for the report i made yesterday",
        # action phrasings that must reach their action pipelines
        "can you change my desktop wallpaper to C:\\pics\\w.jpg",
        "set the wallpaper to sunset.jpg",
        "how many icons do i have on my desktop?",
    ]:
        plan = plan_observation(q)
        assert not (plan and plan.action_type == "search_files"), f"over-triggered: {q}"


def test_more_pronoun_followups_resolve():
    ctx = ["do i have a song called tema ensingo on my pc"]
    for q in ["where is it?", "find it", "is it on my pc?", "where did i save it"]:
        plan = plan_observation(q, recent_user_messages=ctx)
        assert plan is not None, f"missed: {q}"
        assert plan.payload["query"] == "tema ensingo"


def test_export_chats_redacts_and_includes_all_sections(tmp_path):
    """scripts/export_chats.py: one command produces a shareable file with
    conversations, traces and audit events — home paths redacted."""
    import sqlite3
    from app.database import DatabaseManager
    from scripts.export_chats import export

    db_path = str(tmp_path / "assistant.db")
    db = DatabaseManager(db_path)
    db.add_conversation_message("conv_x", "user", "do i have a song called kaba")
    db.add_conversation_message("conv_x", "assistant", f"Found it at {tmp_path}\\Music\\kaba.mp3")

    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cognitive_traces (trace_id TEXT, user_input TEXT,"
        " assistant_reply TEXT, model_used TEXT, latency_ms REAL, goal_verified INTEGER,"
        " goal_lifecycle_state TEXT, gate_decision TEXT, created_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " timestamp TEXT, action TEXT, status TEXT, details TEXT, level INTEGER)"
    )
    conn.execute(
        "INSERT INTO cognitive_traces (trace_id, user_input, assistant_reply, model_used,"
        " latency_ms, goal_verified, created_at) VALUES (?,?,?,?,?,?,?)",
        ("trace_t1", "do i have a song called kaba", "yes", "fast", 12.5, 1, "t"),
    )
    conn.execute(
        "INSERT INTO audit_logs (timestamp, action, status, details, level) VALUES (?,?,?,?,?)",
        ("t", "create_task", "success", str(tmp_path / "secret"), 0),
    )
    conn.commit()
    conn.close()

    out = tmp_path / "export.md"
    export(db_path, str(out), messages=10, traces=5, audits=5, full=False,
           redact=True, home=str(tmp_path))
    text = out.read_text(encoding="utf-8")

    assert "do i have a song called kaba" in text
    assert "conv_x" in text
    assert "trace_t1" in text and "goal_verified=yes" in text
    assert "create_task" in text
    # Home/tmp paths must not leak verbatim.
    assert str(tmp_path) not in text


def test_host_context_patterns_beat_broad_file_block():
    """Specialized host patterns (desktop, downloads) keep their questions
    even though the broad file matcher also smells a file."""
    import app.cognition.observation_router as obr
    with patch("app.cognition.observation_router._desktop_directories",
               return_value=["/tmp/Desktop"]):
        plan = plan_observation("how many files do i have on my desktop?")
        assert plan.question_kind == "desktop_contents"
    plan = plan_observation("what's in my downloads folder")
    assert plan.question_kind == "downloads_folder"


def test_export_failure_phrases_from_live_chats():
    """Every misrouted phrasing from the owner's real chat export (2026-08-29)
    routes to evidence now. Each line cites the live failure it prevents."""
    ctx = ["do i have a song called kaba on my pc"]

    # 12:37 — 'the system cannot verify this directly as it lacks current
    # evidence from your desktop. Could you please highlight or click...'
    plan = plan_observation("im looking for a song called kaba")
    assert plan is not None and plan.action_type == "search_files"
    assert plan.payload["query"] == "kaba"

    # 12:36 — 38s of LLM flailing, 'could you please describe what kind of
    # song', goal parked as waiting_for_evidence.
    plan = plan_observation(
        "i want to know where the song i asked is located", recent_user_messages=ctx
    )
    assert plan is not None and plan.question_kind == "file_location"
    assert plan.payload["query"] == "kaba"

    plan = plan_observation("where's the song i asked about?", recent_user_messages=ctx)
    assert plan is not None and plan.question_kind == "file_location"

    # 13:11 — 'let's observe the list of applications...' non-answer.
    # (games questions now use the more precise installed_games kind, which
    # renders a filtered, countable game list instead of an app sample)
    for q in ("how many games do i have on my pc", "what games do i have installed"):
        plan = plan_observation(q)
        assert plan is not None and plan.question_kind in ("installed_apps", "installed_games")

    # 11:35 — answered with the tzdata 'Europe\\London' folder; the hint must
    # steer the model to actual media files.
    plan = plan_observation("do i have a song called london on my pc")
    assert plan.question_kind == "file_existence"
    assert "prioritize matching media" in plan.evidence_hint

    # Reference tails must not read as content intent.
    assert plan_observation("tell me all about the song called yesterday") is None
    assert plan_observation("tell me about the song called london") is None


def test_games_questions_get_game_aware_evidence():
    """Live bug: 'how can i check my games on pc' got File Explorer
    instructions from the LLM while the app-inventory scan sat unused — and
    even routed games questions only got '613 apps, sample of 10', which
    cannot be counted. Any non-action game question now routes with a
    filtered, countable game list."""
    routes = [
        "how many games do i have on my pc", "what games do i have",
        "where are my games", "how can i check my games on pc",
        "check my games", "can you check my games",
        "where are my games stored", "how do i see my games",
        "do i have a game called minecraft",
    ]
    for q in routes:
        plan = plan_observation(q)
        assert plan is not None and plan.question_kind == "installed_games", f"missed: {q}"
        assert plan.action_type == "list_apps"

    # Action/content game requests keep their pipelines.
    for q in ["play minecraft", "install fortnite",
              "tell me about the witcher 3 game",
              "where can i watch game of thrones"]:
        plan = plan_observation(q)
        assert plan is None or plan.question_kind != "installed_games", f"over-triggered: {q}"

    # Evidence must list the games so the model can count them.
    fake = {"success": True, "applications": [
        {"app_name": "Epic Games Launcher", "source_category": "Start Menu"},
        {"app_name": "Football Manager 2024", "source_category": "Start Menu"},
        {"app_name": "Microsoft Word", "source_category": "Start Menu"},
        {"app_name": "Minecraft Launcher", "source_category": "Start Menu"},
    ]}
    plan = plan_observation("how many games do i have on my pc")
    ev = render_observation_evidence(fake, plan)
    assert "3 look like games" in ev
    assert "Epic Games Launcher" in ev and "Football Manager 2024" in ev
    assert "Microsoft Word" not in ev
    assert "count/list the games" in ev


def test_capability_questions_answer_from_tool_registry():
    """'Can you access my computer / use it for tasks?' kept producing 'I
    don't have access' apologies. The fact is observable: the tool registry."""
    routes = [
        "can you access my computer",
        "can you use the computer for tasks",
        "can you control my pc",
        "do you have access to my files",
    ]
    for q in routes:
        plan = plan_observation(q)
        assert plan is not None and plan.question_kind == "capability_selfcheck", f"missed: {q}"
        assert plan.action_type == "list_capabilities"

    # Action requests and the screen pattern are NOT capability questions.
    assert plan_observation("can you see my desktop").question_kind == "screen_contents"
    for q in ["can you open the file called report", "can you play music"]:
        plan = plan_observation(q)
        assert plan is None or plan.question_kind != "capability_selfcheck", q

    from app.tools.manifest import get_tool_manifest
    res = get_tool_manifest()["list_capabilities"]["handler"]({})
    assert res["success"] and res["tool_count"] > 20
    assert "filesystem" in res["categories"] and "search_files" in res["categories"]["filesystem"]

    ev = render_observation_evidence(res, plan_observation("can you access my computer"))
    assert "registered tools" in ev
    assert "NEVER claim it cannot access" in ev


def test_internet_capability_questions_answer_from_tool_registry():
    """Live transcript: 'can you access the internet' got 'without direct
    internet connectivity ... I can't confirm' — while the registry holds
    web_search, browser sessions, ping/DNS. Route these to list_capabilities
    with an internet-focused evidence answer."""
    routes = [
        "can you access the internet",
        "do you have internet access",
        "do you have internet",
        "can you browse the web",
        "can you go online",
        "can you search the web",
        "are you connected to the internet",
        "are you online",
        "is there internet",
    ]
    for q in routes:
        plan = plan_observation(q)
        assert plan is not None and plan.question_kind == "capability_selfcheck", f"missed: {q}"
        assert plan.action_type == "list_capabilities", q
        assert plan.payload.get("focus") == "internet", q

    # Polite TASKS are not capability questions — ' for ' marks a real request.
    for q in [
        "can you search the web for the best laptop",
        "search the web for weather in kampala",
        "browse the web for me",
    ]:
        plan = plan_observation(q)
        assert plan is None or plan.question_kind != "capability_selfcheck", q

    # Local-machine access questions keep the non-internet evidence focus.
    assert plan_observation("can you access my computer").payload.get("focus") is None

    from app.tools.manifest import get_tool_manifest
    res = get_tool_manifest()["list_capabilities"]["handler"]({})
    ev = render_observation_evidence(res, plan_observation("can you access the internet"))
    assert "web_search" in ev, "internet evidence must name the actual web tools"
    assert "NEVER claim it has no internet access" in ev
    # The local-access evidence text must be unchanged.
    ev_local = render_observation_evidence(res, plan_observation("can you access my computer"))
    assert "NEVER claim it cannot access" in ev_local


def test_conversational_answers_include_history(tmp_path):
    """Live transcript: 'can you answer the question i asked last now' got a
    hallucinated Windows-Defender task — the ANSWER branch sent the LLM only
    the current message. Prior turns must now be in the messages payload."""
    import app.llm as llm_mod
    from app.cognition.runtime import CognitiveRuntime

    captured = {}

    def fake_generate(messages=None, complexity="fast", max_tokens=150, **kw):
        captured["messages"] = messages
        return {"choices": [{"message": {"content": "The word was pinecone."}}],
                "model": "qwen2.5-3b-instruct"}

    runtime = CognitiveRuntime(db_path=str(tmp_path / "rt.db"))
    history = [
        {"role": "user", "content": "remember the word pinecone"},
        {"role": "assistant", "content": "Got it — pinecone."},
        {"role": "user", "content": "thanks"},
        {"role": "assistant", "content": "Anytime."},
    ]
    with patch.object(llm_mod.llm_client, "generate_chat_completion",
                      side_effect=fake_generate):
        res = runtime.process_cognitive_cycle(
            "what was the word i asked you to remember",
            conversation_history=history,
        )
        assert res.get("success") is True or res.get("request_success") is True, res

        msgs = captured["messages"]
        roles = [m["role"] for m in msgs]
        # System first, current user turn LAST, history in between.
        assert roles[0] == "system" and roles[-1] == "user"
        assert "remember the word pinecone" in [m["content"] for m in msgs]
        assert "what was the word i asked you to remember" == msgs[-1]["content"]

        # Without history the payload is exactly system + current turn.
        captured.clear()
        runtime.process_cognitive_cycle("what is the capital of france")
        assert len(captured["messages"]) == 2


def test_evidence_answers_use_main_model(tmp_path):
    """Evidence-grounded answers are routed to the MAIN model: the small
    model demonstrably fumbled them ('I can't access your computer' with
    evidence in context)."""
    import app.llm as llm_mod
    from app.cognition.runtime import CognitiveRuntime

    captured = {}

    def fake_generate(messages=None, complexity="fast", max_tokens=150, **kw):
        captured["complexity"] = complexity
        return {"choices": [{"message": {"content": "Found 2 files."}}],
                "model": "qwen2.5-9b-instruct"}

    runtime = CognitiveRuntime(db_path=str(tmp_path / "rt.db"))
    with patch.object(llm_mod.llm_client, "generate_chat_completion",
                      side_effect=fake_generate):
        res = runtime.process_cognitive_cycle("do i have a song called kaba on my pc")
        assert res.get("success") is True or res.get("request_success") is True, res
        assert captured["complexity"] == "main", (
            "evidence-grounded answer must use the main model"
        )

        # Non-evidence conversational answers stay on the fast model.
        captured.clear()
        res2 = runtime.process_cognitive_cycle("what is the capital of france")
        assert captured["complexity"] == "fast", (
            "plain conversational answer should keep the fast model"
        )


def test_what_about_followup_routes_to_file_search():
    """Live transcript: 'give me a list of all the songs called kaba' was
    answered from search evidence, then 'what about ordinaryr by alex warren'
    fell to the raw LLM and got an improvised answer. The follow-up must
    trigger another filesystem search when file/music context is present."""
    ctx = ["give me a list of all the songs called kaba in my pc"]

    plan = plan_observation("what about ordinaryr by alex warren", recent_user_messages=ctx)
    assert plan is not None and plan.action_type == "search_files"
    assert plan.payload["query"] == "ordinaryr"
    assert plan.question_kind == "file_search"
    assert "alex warren" in plan.evidence_hint

    # Without the ' by <artist>' tail.
    plan = plan_observation("what about kaba", recent_user_messages=ctx)
    assert plan is not None and plan.payload["query"] == "kaba"

    # Explicit media noun routes even without prior context.
    plan = plan_observation("what about the song ordinary")
    assert plan is not None and plan.action_type == "search_files"
    assert plan.payload["query"] == "ordinary"

    # Pronoun/filler subjects are NOT names — leave them to the LLM path.
    for q in ["how about another one", "what about it", "what about more"]:
        plan = plan_observation(q, recent_user_messages=ctx)
        assert plan is None or plan.question_kind != "file_search", q

    # No file/music context and no media noun -> not a file question.
    plan = plan_observation("what about privacy settings", recent_user_messages=["change my theme"])
    assert plan is None or plan.question_kind != "file_search"
