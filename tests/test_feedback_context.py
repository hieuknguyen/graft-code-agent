"""Regression coverage for terminal feedback losing state and retrying reads."""

from pathlib import Path
from unittest.mock import patch

import pytest

from config import AppConfig
from core.agent import GraftAgent


def reply(text, tokens=10):
    return {"success": True, "response": text, "tokens": {"total_tokens": tokens}}


@pytest.fixture
def agent(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    instance = GraftAgent(AppConfig(web_search=False), str(root))
    with patch("core.environment_inspector.EnvironmentInspector.inspect_project", return_value={"error": "Test environment"}):
        yield instance


def analyze(agent, command="python -m compileall .", output="SyntaxError: invalid command quoting"):
    return agent.analyze_log_and_plan_next("Tách các hàm thành module riêng", command, 1, output)


def test_feedback_remembers_applied_modules_and_recent_failures(agent):
    for filename in ("config.py", "api.py", "storage.py", "plot_btc_weekly.py"):
        assert agent.create_new_file(filename, "# implemented module\n")[0]
    with patch.object(agent.client, "query_ai", return_value=reply("Need a focused verification.")) as query:
        analyze(agent, command="python -c broken", output="unterminated string literal")
        analyze(agent, command="python -m compileall .", output="second attempt")
    prompt = query.call_args.args[0]
    applied_section = prompt.split("=== APPLIED FILE CHANGES", 1)[1].split("=== RECENT COMMAND RESULTS", 1)[0]
    for filename in ("config.py", "api.py", "storage.py", "plot_btc_weekly.py"):
        assert f"created: `{filename}`" in applied_section
    assert "python -c broken" in prompt
    assert "unterminated string literal" in prompt
    assert "second attempt" in prompt


def test_feedback_reads_entire_file_over_terminal_tail_limit_before_returning_actions(agent):
    source = "# beginning of source\n" + ("# source content\n" * 600) + "def answer():\n    return 1\n"
    (agent.root_dir / "module.py").write_text(source, encoding="utf-8")
    draft = """<<<READ_FILE
File: module.py
<<<END_READ_FILE
<<<RUN_COMMAND
Command: echo draft-must-not-run
<<<END_RUN_COMMAND
"""
    repair = """<<<GRAFT_ACTION
Action: REPLACE
File: module.py
Symbol: answer
```python
def answer():
    return 2
```
>>>
<<<RUN_COMMAND
Command: python -m compileall module.py
<<<END_RUN_COMMAND
"""
    with patch.object(agent.client, "query_ai", side_effect=[reply(draft), reply(repair, 20)]) as query:
        result = analyze(agent, output=source)
    assert query.call_count == 2
    assert "[Earlier " in query.call_args_list[0].args[0]
    assert source in query.call_args_list[1].args[0]
    assert "REQUESTED FILE CONTENTS" in query.call_args_list[1].args[0]
    assert result["tokens"]["total_tokens"] == 30
    assert result["commands"] == [{"command": "python -m compileall module.py", "description": ""}]
    assert "return 2" in result["actions"][0]["new_code"]
    assert (agent.root_dir / "module.py").read_text(encoding="utf-8") == source
    assert agent.feedback_progress_revision == 0  # Proposals do not count as applied.


@pytest.mark.parametrize("second_reply", [
    reply("<<<READ_FILE\nFile: still_missing.py\n<<<END_READ_FILE"),
    {"success": False, "error": "Gateway unavailable", "tokens": {"total_tokens": 5}},
    {"success": True, "response": ""},
])
def test_failed_or_repeated_retrieval_never_returns_draft_commands(agent, second_reply):
    draft = """<<<READ_FILE
File: missing.py
<<<END_READ_FILE
<<<RUN_COMMAND
Command: echo should-not-run
<<<END_RUN_COMMAND
"""
    with patch.object(agent.client, "query_ai", side_effect=[reply(draft), second_reply]) as query:
        result = analyze(agent)
    assert query.call_count == 2
    assert result["success"] is False
    assert result["error"]
    assert not result.get("commands")


def test_missing_source_can_be_reported_without_another_terminal_read(agent):
    with patch.object(agent.client, "query_ai", side_effect=[
        reply("<<<READ_FILE\nFile: missing.py\n<<<END_READ_FILE"),
        reply("Không tìm thấy missing.py; chưa thể xác minh bước này."),
    ]) as query:
        result = analyze(agent)
    assert "was not found inside the project" in query.call_args.args[0]
    assert result["commands"] == []
    assert "chưa thể xác minh" in result["response"]


def test_feedback_cannot_read_outside_project(agent, tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("outside-content-must-not-be-read", encoding="utf-8")
    with patch.object(agent.client, "query_ai", side_effect=[
        reply(f"<<<READ_FILE\nFile: {outside}\n<<<END_READ_FILE"),
        reply("Cannot read outside project."),
    ]) as query:
        analyze(agent)
    assert "outside-content-must-not-be-read" not in query.call_args.args[0]


def test_feedback_respects_disabled_web_search(agent):
    with patch.object(agent.runtime, "web_search") as search, \
         patch.object(agent.client, "query_ai", side_effect=[
             reply("<<<WEB_SEARCH\nQuery: dependency error\n<<<END_WEB_SEARCH"),
             reply("External lookup unavailable."),
         ]) as query:
        analyze(agent)
    search.assert_not_called()
    assert "Web search is disabled" in query.call_args.args[0]


@pytest.mark.parametrize("filename", [".env", "credentials.json", ".git/config"])
def test_requested_context_preserves_runtime_read_restrictions(agent, filename):
    path = agent.root_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("restricted-content-must-not-be-read", encoding="utf-8")
    sections = agent._requested_context([filename], [])
    assert "restricted-content-must-not-be-read" not in "\n".join(sections)
    assert "Could not read" in "\n".join(sections)


def test_progress_revision_requires_actual_successful_content_change(agent):
    assert agent.create_new_file("module.py", "answer = 1\n")[0]
    first_revision = agent.feedback_progress_revision
    assert first_revision == 1
    assert agent.create_new_file("module.py", "answer = 1\n")[0]
    assert agent.feedback_progress_revision == first_revision
    action = {"file": "module.py", "original_code": "stale draft", "new_code": "answer = 1\n"}
    assert agent.apply_action(action)[0]
    assert agent.feedback_progress_revision == first_revision
    action["new_code"] = "answer = 2\n"
    assert agent.apply_action(action)[0]
    assert agent.feedback_progress_revision == first_revision + 1
    with patch.object(Path, "write_text", side_effect=OSError("disk full")):
        assert not agent.create_new_file("failed.py", "answer = 3\n")[0]
    assert agent.feedback_progress_revision == first_revision + 1
    assert "failed.py" not in agent._feedback_progress_context()
    assert agent.delete_project_file("module.py")[0]
    assert agent.feedback_progress_revision == first_revision + 2
    assert "deleted: `module.py`" in agent._feedback_progress_context()


def test_new_request_clears_progress_and_feedback_history(agent):
    assert agent.create_new_file("module.py", "answer = 1\n")[0]
    with patch.object(agent.client, "query_ai", return_value=reply("A repair is pending.")):
        analyze(agent, command="old-check", output="old-error")
    agent.begin_task()
    assert agent.feedback_progress_revision == 0
    with patch.object(agent.client, "query_ai", return_value=reply("Done.")) as query:
        analyze(agent, command="new-check", output="new-result")
    context = query.call_args.args[0]
    assert "old-check" not in context
    assert "old-error" not in context
    assert "created: `module.py`" not in context
    assert "new-check" in context


def test_feedback_history_stays_bounded_during_long_tasks(agent):
    with patch.object(agent.client, "query_ai", return_value=reply("Next check.")) as query:
        for index in range(8):
            analyze(agent, command=f"check-{index}", output=f"result-{index}")
    context = query.call_args.args[0]
    assert "check-0" not in context
    assert "check-1" not in context
    assert "check-2" in context
    assert "check-7" in context
