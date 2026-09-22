"""Syntax failures reach the model before any candidate can modify a file."""

import json
from unittest.mock import patch

import pytest

from config import AppConfig
from core.agent import GraftAgent
from core.tool_runtime import ToolRuntime


SOURCE = "def answer():\n    return 1\n"
UPDATED = "def answer():\n    return 2\n"
INVALID = "def answer():\n    return (\n"


def tool_call(name, **arguments):
    return "<<<TOOL_CALL\n" + json.dumps({"name": name, "arguments": arguments}) + "\n<<<END_TOOL_CALL"


def reply(text):
    return {"success": True, "response": text, "tokens": {"total_tokens": 10}}


def create_block(code, path="new_module.py"):
    return f"<<<CREATE_FILE\nFile: {path}\n```python\n{code}```\n<<<END_CREATE_FILE"


def graft_block(code):
    return f"<<<GRAFT_ACTION\nFile: module.py\nAction: REPLACE\nSymbol: answer\n```python\n{code}```\n<<<END_GRAFT_ACTION"


@pytest.fixture
def agent(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "module.py").write_bytes(SOURCE.encode("utf-8"))
    instance = GraftAgent(AppConfig(provider="gateway", web_search=False), str(project))
    instance.scan()
    with patch("core.environment_inspector.EnvironmentInspector.inspect_project", return_value={"error": "Test environment"}):
        yield instance


def invoke(agent, entrypoint):
    if entrypoint == "planning":
        return agent.plan_and_graft("Fix the return value and add a working helper if needed.")
    return agent.analyze_log_and_plan_next(
        "Fix the return value and add a working helper if needed.",
        "python -m compileall .", 1, "Verification failed.",
    )


def test_read_file_automatically_reports_existing_syntax_error(tmp_path):
    target = tmp_path / "broken.py"
    target.write_text(INVALID, encoding="utf-8")
    runtime = ToolRuntime(str(tmp_path))

    with patch.object(runtime, "check_syntax") as manual_check:
        result = runtime.dispatch("read_file", {"path": "broken.py"})

    manual_check.assert_not_called()
    assert result["ok"]
    assert result["syntax"]["status"] == "invalid"
    assert result["syntax"]["language"] == "python"
    assert result["syntax"]["diagnostics"][0]["line"] == 2
    assert "return (" in result["syntax"]["diagnostics"][0]["excerpt"]
    assert target.read_text(encoding="utf-8") == INVALID


@pytest.mark.parametrize("tool", ["edit_file", "edit_file_ranges", "propose_edit_file", "propose_write_file"])
def test_invalid_candidate_has_structured_diagnostics_and_never_becomes_pending(agent, tool):
    runtime = agent.runtime
    snapshot = runtime.read_file("module.py").data
    arguments = {
        "edit_file": {"old_text": "return 1", "new_text": "return ("},
        "edit_file_ranges": {"edits": [{"start_line": 2, "end_line": 2, "new_text": "    return ("}]},
        "propose_edit_file": {
            "edits": [{"old_text": "return 1", "new_text": "return ("}],
            "expected_sha256": snapshot["sha256"],
        },
        "propose_write_file": {"content": INVALID, "expected_sha256": snapshot["sha256"]},
    }[tool]

    result = runtime.dispatch(tool, dict(path="module.py", **arguments))

    assert result["ok"] is False
    assert result["error_code"] == "SYNTAX_ERROR"
    assert result["syntax"]["status"] == "invalid"
    assert result["syntax"]["diagnostics"][0]["line"] == 2
    assert result["retry_hint"]
    assert not runtime._proposals
    assert (agent.root_dir / "module.py").read_bytes() == SOURCE.encode("utf-8")


@pytest.mark.parametrize("entrypoint", ["planning", "feedback"])
@pytest.mark.parametrize("tool", ["edit_file", "edit_file_ranges"])
def test_model_repairs_invalid_edit_using_automatic_diagnostics(agent, entrypoint, tool):
    if tool == "edit_file":
        invalid = tool_call(tool, path="module.py", old_text="return 1", new_text="return (")
        corrected = tool_call(tool, path="module.py", old_text="return 1", new_text="return 2")
    else:
        invalid = tool_call(tool, path="module.py", edits=[{"start_line": 2, "end_line": 2, "new_text": "    return ("}])
        corrected = tool_call(tool, path="module.py", edits=[{"start_line": 2, "end_line": 2, "new_text": "    return 2"}])
    responses = [
        reply(tool_call("read_file", path="module.py")), reply(invalid),
        reply(corrected), reply("The correction is ready to review."),
    ]

    with patch.object(agent.runtime, "check_syntax") as manual_check, \
         patch.object(agent.client, "query_ai", side_effect=responses) as query:
        result = invoke(agent, entrypoint)

    manual_check.assert_not_called()
    assert query.call_count == 4
    feedback = query.call_args_list[2].args[0]
    assert '"error_code": "SYNTAX_ERROR"' in feedback
    assert '"line": 2' in feedback
    assert "return (" in feedback
    assert result["success"]
    assert len(result["actions"]) == 1
    assert result["actions"][0]["new_code"] == UPDATED
    assert result["actions"][0]["original_code"] == SOURCE
    assert not result["commands"]
    assert len(agent.runtime._proposals) == 1
    assert (agent.root_dir / "module.py").read_bytes() == SOURCE.encode("utf-8")
    assert agent.apply_action(result["actions"][0])[0]
    assert (agent.root_dir / "module.py").read_text(encoding="utf-8") == UPDATED


@pytest.mark.parametrize("entrypoint", ["planning", "feedback"])
@pytest.mark.parametrize("kind", ["create", "graft"])
def test_legacy_candidate_gets_automatic_syntax_repair_before_delivery(agent, entrypoint, kind):
    block = create_block if kind == "create" else graft_block
    with patch.object(agent.runtime, "check_syntax") as manual_check, \
         patch.object(agent.client, "query_ai", side_effect=[reply(block(INVALID)), reply(block(UPDATED))]) as query:
        result = invoke(agent, entrypoint)

    manual_check.assert_not_called()
    assert query.call_count == 2
    feedback = query.call_args_list[1].args[0]
    assert "AUTOMATIC SYNTAX FEEDBACK" in feedback
    assert '"line": 2' in feedback
    assert "return (" in feedback
    assert result["success"]
    assert result["tokens"]["total_tokens"] == 20
    assert (agent.root_dir / "module.py").read_bytes() == SOURCE.encode("utf-8")
    assert not (agent.root_dir / "new_module.py").exists()
    if kind == "create":
        assert len(result["create_files"]) == 1
        assert result["create_files"][0]["code"].strip() == UPDATED.strip()
    else:
        assert len(result["actions"]) == 1
        assert result["actions"][0]["success"]
        assert result["actions"][0]["new_code"] == UPDATED


@pytest.mark.parametrize("entrypoint", ["planning", "feedback"])
@pytest.mark.parametrize("followup", ["invalid", "prose"])
def test_legacy_unresolved_syntax_stops_after_two_repairs_and_cannot_claim_done(agent, entrypoint, followup):
    invalid = create_block(INVALID) + "\n<<<RUN_COMMAND\nCommand: echo must-not-run\n<<<END_RUN_COMMAND"
    subsequent = invalid if followup == "invalid" else "Everything has been fixed successfully."
    with patch.object(agent.client, "query_ai", side_effect=[reply(invalid), reply(subsequent), reply(subsequent)]) as query:
        result = invoke(agent, entrypoint)

    assert query.call_count == 3
    assert result["success"] is False
    assert "2" in result["error"]
    assert "new_module.py" in result["error"]
    assert result["tokens"]["total_tokens"] == 30
    assert not result.get("commands")
    assert not result.get("actions")
    assert not result.get("create_files")
    assert not (agent.root_dir / "new_module.py").exists()


def test_tool_syntax_error_cannot_be_erased_by_a_prose_completion(agent):
    responses = [
        reply(tool_call("read_file", path="module.py")),
        reply(tool_call("edit_file", path="module.py", old_text="return 1", new_text="return (")),
        *[reply("The file is fixed now.") for _ in range(3)],
    ]
    with patch.object(agent.client, "query_ai", side_effect=responses) as query:
        result = invoke(agent, "planning")
    assert query.call_count == 5
    assert result["success"] is False
    assert "module.py" in result["error"]
    assert not result.get("actions")
    assert not agent.runtime._proposals
    assert (agent.root_dir / "module.py").read_bytes() == SOURCE.encode("utf-8")


@pytest.mark.parametrize("exists", [False, True])
def test_direct_create_rejects_invalid_code_before_creating_directories_or_backups(agent, exists):
    path = "module.py" if exists else "new_directory/new_module.py"
    success, message = agent.create_new_file(path, INVALID)
    assert success is False
    assert "2" in message
    assert not agent.history_backups
    assert not (agent.root_dir / "new_directory").exists()
    assert (agent.root_dir / "module.py").read_bytes() == SOURCE.encode("utf-8")
    assert agent.feedback_progress_revision == 0


def test_direct_legacy_apply_rejects_invalid_code_without_backup_or_progress(agent):
    success, message = agent.apply_action({"file": "module.py", "original_code": SOURCE, "new_code": INVALID})
    assert success is False
    assert "2" in message
    assert (agent.root_dir / "module.py").read_bytes() == SOURCE.encode("utf-8")
    assert not agent.history_backups
    assert agent.feedback_progress_revision == 0


def test_apply_revalidates_stored_candidate_before_writing(agent):
    runtime = agent.runtime
    runtime.read_file("module.py")
    proposed = runtime.edit_file("module.py", "return 1", "return 2")
    proposal_id = proposed.data["proposal_id"]
    runtime._proposals[proposal_id].payload["content"] = INVALID

    result = runtime.apply_write(proposal_id)

    assert result.error_code == "SYNTAX_ERROR"
    assert result.data["syntax"]["diagnostics"][0]["line"] == 2
    assert (agent.root_dir / "module.py").read_bytes() == SOURCE.encode("utf-8")


def test_unsupported_language_is_reported_as_unavailable_instead_of_valid(agent):
    target = agent.root_dir / "source.custom_language"
    target.write_text("old source", encoding="utf-8")
    responses = [
        reply(tool_call("read_file", path=target.name)),
        reply(tool_call("edit_file", path=target.name, old_text="old source", new_text="new source")),
        reply("The change is ready; syntax checking is unavailable for this file type."),
    ]
    with patch.object(agent.client, "query_ai", side_effect=responses):
        result = invoke(agent, "planning")
    assert result["success"]
    assert len(result["actions"]) == 1
    assert len(result["syntax_warnings"]) == 1
    warning = result["syntax_warnings"][0]
    assert warning["path"] == target.name
    assert warning["syntax"]["status"] == "unavailable"
    assert warning["syntax"]["checked"] is False
    assert target.read_text(encoding="utf-8") == "old source"


@pytest.mark.parametrize("entrypoint", ["planning", "feedback"])
def test_failed_syntax_repair_after_legacy_read_does_not_release_abandoned_actions(agent, entrypoint):
    initial = ("<<<READ_FILE\nFile: module.py\n<<<END_READ_FILE\n" + create_block(UPDATED)
               + "\n<<<RUN_COMMAND\nCommand: echo abandoned-draft\n<<<END_RUN_COMMAND")
    with patch.object(agent.client, "query_ai", side_effect=[
        reply(initial), reply(create_block(INVALID)), reply(create_block(INVALID)), reply(create_block(INVALID)),
    ]) as query:
        result = invoke(agent, entrypoint)
    assert query.call_count == 4
    assert not result["success"]
    assert "cú pháp" in result["error"]
    assert not result.get("create_files")
    assert not result.get("commands")
    assert not (agent.root_dir / "new_module.py").exists()


def test_legacy_read_also_automatically_reports_syntax(agent):
    (agent.root_dir / "module.py").write_text(INVALID, encoding="utf-8")
    sections = agent._requested_context(["module.py"], [])
    assert "AUTOMATIC SYNTAX DIAGNOSTICS" in sections[0]
    assert '"status": "invalid"' in sections[0]
    assert '"line": 2' in sections[0]


def test_repeated_legacy_read_cannot_hide_invalid_create_behind_retrieval_limit(agent):
    draft = ("<<<READ_FILE\nFile: module.py\n<<<END_READ_FILE\n" + create_block(INVALID)
             + "\n<<<RUN_COMMAND\nCommand: echo abandoned-draft\n<<<END_RUN_COMMAND")
    with patch.object(agent.client, "query_ai", return_value=reply(draft)) as query:
        result = invoke(agent, "planning")
    assert query.call_count == 2
    assert not result["success"]
    assert not result.get("commands")
    assert not result.get("create_files")


def test_read_pagination_never_skips_complete_lines_when_context_is_full(tmp_path):
    from core.tool_runtime import MAX_READ_CHARS
    path = tmp_path / "wide.txt"
    path.write_text("a" * (MAX_READ_CHARS // 2) + "\nsecond line\n" + "b" * (MAX_READ_CHARS // 2) + "\nlast line\n", encoding="utf-8")
    runtime = ToolRuntime(str(tmp_path))
    first = runtime.read_file(path.name).data
    assert first["end_line"] == 2
    assert first["next_start_line"] == 3
    assert first["partial_line"] is None
    second = runtime.read_file(path.name, start_line=first["next_start_line"]).data
    assert second["start_line"] == 3
    assert second["end_line"] == 4
    assert "last line" in second["content"]
