"""Gateway tool turns must collect evidence and proposals without applying drafts."""

import hashlib
import json
from unittest.mock import patch

import pytest

from config import AppConfig
from core.agent import GraftAgent
from core.gemini_agent import GeminiCodingAgent


SOURCE = "def answer():\n    return 1\n"
SOURCE_HASH = hashlib.sha256(SOURCE.encode("utf-8")).hexdigest()
UPDATED = "def answer():\n    return 2\n"


def tool_call(name, **arguments):
    payload = json.dumps({"name": name, "arguments": arguments})
    return f"<<<TOOL_CALL\n{payload}\n<<<END_TOOL_CALL"


def reply(text, tokens=10):
    return {
        "success": True,
        "response": text,
        "tokens": {"total_tokens": tokens, "prompt_tokens": tokens - 1, "completion_tokens": 1},
    }


def edit_call():
    return tool_call(
        "propose_edit_file",
        path="module.py",
        edits=[{"old_text": "return 1", "new_text": "return 2"}],
        expected_sha256=SOURCE_HASH,
        description="Correct the return value.",
    )


@pytest.fixture
def agent(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "module.py").write_bytes(SOURCE.encode("utf-8"))
    instance = GraftAgent(AppConfig(provider="gateway", web_search=False), str(project))
    instance.scan()
    with patch(
        "core.environment_inspector.EnvironmentInspector.inspect_project",
        return_value={"error": "Test environment"},
    ):
        yield instance


def invoke(agent, entrypoint, task="Only explain what the code does; do not modify files."):
    if entrypoint == "planning":
        return agent.plan_and_graft(task)
    return agent.analyze_log_and_plan_next(task, "python -m compileall .", 1, "Verification failed.")


@pytest.mark.parametrize("entrypoint", ["planning", "feedback"])
def test_tools_find_read_and_propose_edit_without_writing(agent, entrypoint):
    answers = [
        reply(tool_call("find_files", pattern="**/*.py"), 10),
        reply(tool_call("read_file", path="module.py"), 20),
        reply(edit_call(), 30),
        reply("The correction is ready to review.", 40),
    ]
    with patch.object(agent.client, "query_ai", side_effect=answers) as query:
        result = invoke(agent, entrypoint, task="Fix the incorrect return value.")

    assert query.call_count == 4
    assert result["success"] is True
    assert "module.py" in query.call_args_list[1].args[0]
    assert SOURCE_HASH in query.call_args_list[2].args[0]
    assert "return 1" in query.call_args_list[2].args[0]
    assert "proposal_id" in query.call_args_list[3].args[0]
    assert "ACTION DELIVERY CORRECTION" not in query.call_args_list[3].args[0]
    assert len(result["actions"]) == 1
    action = result["actions"][0]
    assert action["file"] == "module.py"
    assert action["proposal_id"]
    assert action["original_code"] == SOURCE
    assert action["new_code"] == UPDATED
    assert action["success"] is True
    assert result["tokens"] == {"total_tokens": 100, "prompt_tokens": 96, "completion_tokens": 4}
    assert not result.get("action_warning")
    assert not result["create_files"]
    assert not result["delete_files"]
    assert not result["commands"]
    assert (agent.root_dir / "module.py").read_bytes() == SOURCE.encode("utf-8")
    assert agent.feedback_progress_revision == 0


@pytest.mark.parametrize("entrypoint", ["planning", "feedback"])
def test_simple_edit_is_applied_without_terminal_commands(agent, entrypoint):
    answers = [
        reply(tool_call("read_file", path="module.py")),
        reply(tool_call("edit_file", path="module.py", old_text="return 1", new_text="return 2")),
        reply("The file edit is ready."),
    ]
    with patch.object(agent.client, "query_ai", side_effect=answers):
        result = invoke(agent, entrypoint, "Fix the incorrect return value.")
    assert result["success"]
    assert not result["commands"]
    assert len(result["actions"]) == 1
    assert (agent.root_dir / "module.py").read_bytes() == SOURCE.encode("utf-8")
    assert agent.apply_action(result["actions"][0])[0]
    assert (agent.root_dir / "module.py").read_text(encoding="utf-8") == UPDATED


def test_simple_edit_accepts_source_from_legacy_read_file(agent):
    answers = [reply("<<<READ_FILE\nFile: module.py\n<<<END_READ_FILE"),
               reply(tool_call("edit_file", path="module.py", old_text="return 1", new_text="return 2")),
               reply("The edit is ready.")]
    with patch.object(agent.client, "query_ai", side_effect=answers):
        result = agent.plan_and_graft("Fix the incorrect return value.")
    assert result["success"] and len(result["actions"]) == 1


def test_simple_edit_recovers_when_model_forgot_to_read_first(agent):
    edit = tool_call("edit_file", path="module.py", old_text="return 1", new_text="return 2")
    answers = [reply(edit), reply(tool_call("read_file", path="module.py")), reply(edit), reply("The edit is ready.")]
    with patch.object(agent.client, "query_ai", side_effect=answers) as query:
        result = agent.plan_and_graft("Fix the incorrect return value.")
    assert "READ_REQUIRED" in query.call_args_list[1].args[0]
    assert result["success"] and len(result["actions"]) == 1


@pytest.mark.parametrize("entrypoint", ["planning", "feedback"])
def test_simple_edit_can_reread_after_a_real_external_change(agent, entrypoint):
    read = tool_call("read_file", path="module.py")
    edit = tool_call("edit_file", path="module.py", old_text="return 1", new_text="return 2")
    calls = 0

    def answer(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            (agent.root_dir / "module.py").write_bytes((SOURCE + "# independent change\n").encode("utf-8"))
        return reply([read, edit, read, edit, "The edit is ready."][calls - 1])

    with patch.object(agent.client, "query_ai", side_effect=answer):
        result = invoke(agent, entrypoint, "Fix the incorrect return value.")
    assert calls == 5
    assert result["success"]
    assert "# independent change" in result["actions"][0]["new_code"]
    assert agent.apply_action(result["actions"][0])[0]


def test_two_simple_edits_with_path_aliases_do_not_make_conflicting_cards(agent):
    answers = [reply(tool_call("read_file", path="module.py")),
               reply(tool_call("edit_file", path="module.py", old_text="return 1", new_text="return 2")),
               reply(tool_call("edit_file", path=" ./module.py ", old_text="return 1", new_text="return 3")),
               reply("Keep the first proposal.")]
    with patch.object(agent.client, "query_ai", side_effect=answers) as query:
        result = agent.plan_and_graft("Fix the incorrect return value.")
    assert result["success"] and len(result["actions"]) == 1
    assert "PENDING_EDIT" in query.call_args.args[0]
    assert result["actions"][0]["new_code"] == UPDATED


@pytest.mark.parametrize("entrypoint", ["planning", "feedback"])
def test_actions_emitted_with_a_tool_request_are_discarded(agent, entrypoint):
    draft = tool_call("read_file", path="module.py") + """
<<<CREATE_FILE
File: draft.py
```python
raise RuntimeError('unreviewed draft')
```
<<<END_CREATE_FILE
<<<RUN_COMMAND
Command: echo draft-must-not-run
<<<END_RUN_COMMAND
"""
    with patch.object(agent.client, "query_ai", side_effect=[reply(draft), reply("Inspection complete.")]):
        result = invoke(agent, entrypoint)
    assert result["success"] is True
    assert not result["commands"]
    assert not result["create_files"]
    assert not result["actions"]
    assert not (agent.root_dir / "draft.py").exists()


def test_feedback_can_inspect_symbols_and_syntax_in_one_batch(agent):
    batch = "\n".join([
        tool_call("list_symbols", path="module.py"),
        tool_call("read_symbol", path="module.py", symbol="answer"),
        tool_call("check_syntax", path="module.py"),
    ])
    with patch.object(agent.runtime, "list_symbols", wraps=agent.runtime.list_symbols) as symbols, \
         patch.object(agent.runtime, "read_symbol", wraps=agent.runtime.read_symbol) as read, \
         patch.object(agent.runtime, "check_syntax", wraps=agent.runtime.check_syntax) as syntax, \
         patch.object(agent.client, "query_ai", side_effect=[reply(batch), reply("The function has valid syntax.")]) as query:
        result = invoke(agent, "feedback")
    symbols.assert_called_once_with(path="module.py")
    read.assert_called_once_with(path="module.py", symbol="answer")
    syntax.assert_called_once_with(path="module.py")
    assert query.call_count == 2
    continuation = query.call_args_list[1].args[0]
    assert SOURCE_HASH in continuation
    assert "return 1" in continuation
    assert '"valid": true' in continuation
    assert result["success"] is True
    assert not result["actions"]
    assert result["tokens"]["total_tokens"] == 20


@pytest.mark.parametrize("entrypoint", ["planning", "feedback"])
def test_identical_tool_retry_stops_without_repeating_io(agent, entrypoint):
    request = reply(tool_call("read_file", path="module.py"))
    with patch.object(agent.runtime, "read_file", wraps=agent.runtime.read_file) as read, \
         patch.object(agent.client, "query_ai", return_value=request) as query:
        result = invoke(agent, entrypoint)
    assert result["success"] is False
    assert result["error"]
    assert query.call_count == 2
    assert read.call_count == 1
    assert result["tokens"]["total_tokens"] == 20
    assert not result.get("commands")
    assert not result.get("actions")


@pytest.mark.parametrize("entrypoint", ["planning", "feedback"])
def test_tool_rounds_are_bounded_even_when_arguments_keep_changing(agent, entrypoint):
    answers = [reply(tool_call("read_file", path=f"missing_{index}.py")) for index in range(6)]
    with patch.object(agent.runtime, "read_file", wraps=agent.runtime.read_file) as read, \
         patch.object(agent.client, "query_ai", side_effect=answers) as query:
        result = invoke(agent, entrypoint)
    assert result["success"] is False
    assert result["error"]
    assert read.call_count == 4
    assert query.call_count == 5
    assert result["tokens"]["total_tokens"] == 50
    assert not result.get("commands")


@pytest.mark.parametrize("entrypoint", ["planning", "feedback"])
def test_oversized_tool_batch_cannot_bypass_call_limit(agent, entrypoint):
    batch = "\n".join(tool_call("read_file", path=f"missing_{index}.py") for index in range(9))
    with patch.object(agent.runtime, "read_file", wraps=agent.runtime.read_file) as read, \
         patch.object(agent.client, "query_ai", return_value=reply(batch)) as query:
        result = invoke(agent, entrypoint)
    assert result["success"] is False
    assert result["error"]
    assert read.call_count <= 8
    assert query.call_count <= 2
    assert not result.get("commands")


@pytest.mark.parametrize("entrypoint", ["planning", "feedback"])
@pytest.mark.parametrize("tool_request", [
    "<<<TOOL_CALL\n{bad json}\n<<<END_TOOL_CALL",
    tool_call("unknown_tool", path="module.py"),
    tool_call("read_file", path="../outside.py"),
])
def test_invalid_tool_requests_return_errors_to_model_without_leaking_files(agent, entrypoint, tool_request):
    outside = agent.root_dir.parent / "outside.py"
    outside.write_text("outside-content-must-not-be-read", encoding="utf-8")
    with patch.object(agent.client, "query_ai", side_effect=[
        reply(tool_request), reply("The requested inspection is unavailable."),
    ]) as query:
        result = invoke(agent, entrypoint)
    assert query.call_count == 2
    continuation = query.call_args_list[1].args[0]
    assert '"error"' in continuation
    assert "outside-content-must-not-be-read" not in continuation
    assert result["success"] is True
    assert not result["commands"]
    assert not result["actions"]


@pytest.mark.parametrize("method", [
    "apply_write", "apply_delete", "approve_command", "propose_run_command", "propose_powershell",
])
def test_tool_dispatch_cannot_call_runtime_approval_or_application_methods(agent, method):
    request = tool_call(method, proposal_id="not-approved")
    with patch.object(agent.runtime, method) as forbidden, \
         patch.object(agent.client, "query_ai", side_effect=[reply(request), reply("Cannot call that tool.")]) as query:
        result = agent.plan_and_graft("Only explain the available tools; do not modify files.")
    forbidden.assert_not_called()
    assert query.call_count == 2
    assert '"error"' in query.call_args_list[1].args[0]
    assert result["success"] is True
    assert not result["actions"]
    assert not result["commands"]


@pytest.mark.parametrize("entrypoint", ["planning", "feedback"])
def test_repeated_malformed_tool_calls_stop_at_the_round_limit(agent, entrypoint):
    malformed = "<<<TOOL_CALL\n{bad json}\n<<<END_TOOL_CALL"
    with patch.object(agent.runtime, "dispatch") as dispatch, \
         patch.object(agent.client, "query_ai", return_value=reply(malformed)) as query:
        result = invoke(agent, entrypoint)
    dispatch.assert_not_called()
    assert query.call_count == 5
    assert result["success"] is False
    assert result["error"]
    assert result["tokens"]["total_tokens"] == 50
    assert not result.get("commands")


def test_gateway_failure_during_tool_followup_keeps_tokens_and_discards_draft(agent):
    request = tool_call("read_file", path="module.py")
    failure = {"success": False, "error": "Gateway unavailable", "tokens": {"total_tokens": 5}}
    with patch.object(agent.client, "query_ai", side_effect=[reply(request), failure]):
        result = agent.plan_and_graft("Fix the incorrect return value.")
    assert result["success"] is False
    assert "Gateway unavailable" in result["error"]
    assert result["tokens"]["total_tokens"] == 15
    assert not result.get("commands")
    assert not result.get("actions")


def test_edit_proposal_applies_through_stored_proposal_and_supports_undo(agent):
    with patch.object(agent.client, "query_ai", side_effect=[reply(edit_call()), reply("Ready to review.")]):
        result = agent.plan_and_graft("Fix the incorrect return value.")
    action = result["actions"][0]
    assert (agent.root_dir / "module.py").read_bytes() == SOURCE.encode("utf-8")
    action["new_code"] = "raise RuntimeError('caller altered display payload')\n"
    success, message = agent.apply_action(action)
    assert success, message
    assert (agent.root_dir / "module.py").read_text(encoding="utf-8") == UPDATED
    assert agent.feedback_progress_revision == 1
    assert agent.undo_last()[0]
    assert (agent.root_dir / "module.py").read_text(encoding="utf-8") == SOURCE


def test_stale_edit_proposal_never_overwrites_a_newer_file(agent):
    with patch.object(agent.client, "query_ai", side_effect=[reply(edit_call()), reply("Ready to review.")]):
        result = agent.plan_and_graft("Fix the incorrect return value.")
    newest = "def answer():\n    return 'user changed this meanwhile'\n"
    target = agent.root_dir / "module.py"
    target.write_text(newest, encoding="utf-8")
    success, message = agent.apply_action(result["actions"][0])
    assert not success
    assert message
    assert target.read_text(encoding="utf-8") == newest
    assert not agent.history_backups
    assert agent.feedback_progress_revision == 0


def test_undo_tool_edit_restores_exact_bom_and_windows_newlines(agent):
    raw = b"\xef\xbb\xbfdef answer():\r\n    return 1\r\n"
    target = agent.root_dir / "module.py"
    target.write_bytes(raw)
    proposed = agent.runtime.propose_edit_file(
        "module.py", [{"old_text": "return 1", "new_text": "return 2"}], hashlib.sha256(raw).hexdigest(),
    )
    result = agent._proposals_for_result({"proposal_ids": [proposed.data["proposal_id"]]})
    assert agent.apply_action(result["actions"][0])[0]
    assert target.read_bytes() == raw.replace(b"return 1", b"return 2")
    assert agent.undo_last()[0]
    assert target.read_bytes() == raw


def test_identical_runtime_write_does_not_reset_feedback_guard(agent):
    proposed = agent.runtime.propose_write_file("module.py", SOURCE, SOURCE_HASH)
    result = agent._proposals_for_result({"proposal_ids": [proposed.data["proposal_id"]]})
    assert agent.apply_action(result["actions"][0])[0]
    assert agent.feedback_progress_revision == 0


@pytest.mark.parametrize("entrypoint", ["planning", "feedback"])
def test_tool_edit_cannot_be_overwritten_by_legacy_create_in_same_reply(agent, entrypoint):
    conflicting = """<<<CREATE_FILE
File: ./module.py
```python
print('conflicting replacement')
```
<<<END_CREATE_FILE"""
    with patch.object(agent.client, "query_ai", side_effect=[reply(edit_call()), reply(conflicting)]):
        result = invoke(agent, entrypoint, "Fix the function.")
    assert result["success"] is False
    assert not result.get("actions")
    assert not result.get("create_files")
    assert (agent.root_dir / "module.py").read_bytes() == SOURCE.encode("utf-8")


def test_gemini_exposes_the_shared_coding_tool_schemas():
    declarations = GeminiCodingAgent._tool_schemas()
    schemas = {item["name"]: item["parameters_json_schema"] for item in declarations}
    assert len(schemas) == len(declarations)
    expected = {
        "find_files": {"pattern"},
        "list_symbols": {"path"},
        "read_symbol": {"path", "symbol"},
        "check_syntax": {"path"},
        "propose_edit_file": {"path", "edits", "expected_sha256"},
    }
    for name, required in expected.items():
        schema = schemas[name]
        assert schema["type"] == "object"
        assert required <= set(schema["required"])
        assert required <= set(schema["properties"])
    edit_items = schemas["propose_edit_file"]["properties"]["edits"]["items"]
    assert {"old_text", "new_text"} <= set(edit_items["required"])
    assert not {"apply_write", "apply_delete", "approve_command"} & set(schemas)


def test_shared_tool_schemas_validate_with_installed_gemini_sdk():
    types = pytest.importorskip("google.genai.types")
    declarations = [types.FunctionDeclaration(**item) for item in GeminiCodingAgent._tool_schemas()]
    tool = types.Tool(function_declarations=declarations)
    assert len(tool.function_declarations) == len(declarations)


@pytest.mark.parametrize("name, arguments", [
    ("find_files", {"pattern": "**/*.py"}),
    ("list_symbols", {"path": "module.py"}),
    ("read_symbol", {"path": "module.py", "symbol": "answer"}),
    ("check_syntax", {"path": "module.py"}),
    ("propose_edit_file", {
        "path": "module.py",
        "edits": [{"old_text": "return 1", "new_text": "return 2"}],
        "expected_sha256": SOURCE_HASH,
    }),
])
def test_new_tools_are_available_through_shared_runtime_dispatch(agent, name, arguments):
    result = agent.runtime.dispatch(name, arguments)
    assert result["ok"], result
    assert (agent.root_dir / "module.py").read_bytes() == SOURCE.encode("utf-8")


@pytest.mark.parametrize("handler", ["on_graft_finished", "on_feedback_finished"])
def test_desktop_stale_proposal_stops_dependent_commands(agent, tmp_path, handler):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from core.session_manager import SessionManager
    from desktop.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    agent.config.auto_apply = True
    with patch.object(agent.client, "query_ai", side_effect=[reply(edit_call()), reply("Ready to review.")]):
        result = agent.plan_and_graft("Fix the incorrect return value.")
    result["commands"] = [{"command": "python -m compileall module.py", "description": "Verify"}]
    target = agent.root_dir / "module.py"
    newest = b"# user changed the file\n"
    target.write_bytes(newest)
    with patch("desktop.main_window.SessionManager", return_value=SessionManager(str(tmp_path / "history"))), \
         patch("desktop.main_window.load_config", return_value=agent.config), \
         patch.object(MainWindow, "initial_setup"):
        window = MainWindow(str(agent.root_dir))
        try:
            window.agent = agent
            window.feedback_loop_active = True
            window.current_task = "Fix the incorrect return value."
            with patch.object(window, "_schedule_automatic_command") as schedule:
                getattr(window, handler)(result)
            schedule.assert_not_called()
            assert window.feedback_loop_active is False
            assert window.command_queue == []
            assert target.read_bytes() == newest
            ai_message = next(msg for msg in window.editor.chat_view.raw_messages if msg["role"] == "ai")
            assert ai_message["auto_applied"] is False
            assert any(msg.get("title") == "❌ KHÔNG THỂ ÁP DỤNG THAY ĐỔI" for msg in window.editor.chat_view.raw_messages)
        finally:
            window.on_stop_process_requested()
            window.close()
            window.deleteLater()
            app.processEvents()
