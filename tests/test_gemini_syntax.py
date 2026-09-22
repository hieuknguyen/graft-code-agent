"""Direct Gemini must resolve rejected edits before releasing pending actions."""

import hashlib
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from core.gemini_agent import GeminiCodingAgent
from core.tool_runtime import ToolRuntime


types = pytest.importorskip("google.genai.types")
SOURCE = "def answer():\n    return 1\n"


def function(name, **args):
    return SimpleNamespace(name=name, args=args, id=None)


def response(*calls, text=""):
    parts = [types.Part.from_function_call(name=call.name, args=call.args) for call in calls]
    if text:
        parts.append(types.Part.from_text(text=text))
    return SimpleNamespace(
        function_calls=list(calls), text=text,
        candidates=[SimpleNamespace(content=types.Content(role="model", parts=parts))],
        usage_metadata=SimpleNamespace(prompt_token_count=8, candidates_token_count=2, total_token_count=10),
    )


@pytest.fixture
def runtime(tmp_path):
    (tmp_path / "module.py").write_bytes(SOURCE.encode("utf-8"))
    return ToolRuntime(str(tmp_path))


def run(runtime, responses, rounds=12):
    config = SimpleNamespace(gemini_api_key="test-key", model="test-model", gemini_max_tool_rounds=rounds)
    client = Mock()
    client.models.generate_content.side_effect = responses
    with patch("google.genai.Client", return_value=client), patch.object(runtime, "check_syntax") as syntax:
        result = GeminiCodingAgent(config, runtime).run("Fix the return value and verify the result.")
    syntax.assert_not_called()
    return result, client.models.generate_content


def read():
    return function("read_file", path="module.py")


def invalid():
    return function("edit_file", path="module.py", old_text="return 1", new_text="return (")


def corrected():
    return function("edit_file", path=" ./module.py ", old_text="return 1", new_text="return 2")


def command():
    return function("propose_run_command", program="python", args=["-m", "compileall", "module.py"])


def test_gemini_automatically_reprompts_prose_completion_with_rejected_syntax(runtime):
    result, generate = run(runtime, [
        response(read()), response(invalid(), command()), response(text="It is fixed."),
        response(corrected()), response(text="The correction is ready."),
    ])
    assert generate.call_count == 5
    assert result["success"]
    assert len(result["proposal_ids"]) == 2
    assert result["tokens"]["total_tokens"] == 50
    assert (runtime.root_dir / "module.py").read_text(encoding="utf-8") == SOURCE
    transcript = generate.call_args.kwargs["contents"]
    automatic_feedback = [part.text for item in transcript for part in item.parts if part.text and "AUTOMATIC SYNTAX FEEDBACK" in part.text]
    assert len(automatic_feedback) == 1
    assert '"line": 2' in automatic_feedback[0]
    assert "return (" in automatic_feedback[0]
    assert "original files are unchanged" in automatic_feedback[0]
    proposed = [runtime.proposal_for_ui(item).data for item in result["proposal_ids"]]
    assert [item["kind"] for item in proposed] == ["command", "write"]
    assert proposed[1]["new_code"] == "def answer():\n    return 2\n"


@pytest.mark.parametrize("completion", ["Everything is fixed.", ""])
def test_gemini_unresolved_syntax_withholds_commands_after_two_prose_retries(runtime, completion):
    result, generate = run(runtime, [
        response(read()), response(invalid(), command()),
        *[response(text=completion) for _ in range(3)],
    ])
    assert generate.call_count == 5
    assert result["success"] is False
    assert "2" in result["error"]
    assert "module.py" in result["error"]
    assert "return (" in result["error"]
    assert not result.get("proposal_ids")
    assert result["tokens"]["total_tokens"] == 50
    assert (runtime.root_dir / "module.py").read_text(encoding="utf-8") == SOURCE


def test_gemini_success_on_another_file_cannot_clear_unresolved_edit(runtime):
    (runtime.root_dir / "other.py").write_text("value = 1\n", encoding="utf-8")
    result, generate = run(runtime, [
        response(read(), function("read_file", path="other.py")),
        response(invalid(), function("edit_file", path="other.py", old_text="value = 1", new_text="value = 2"), command()),
        *[response(text="Done.") for _ in range(3)],
    ])
    assert generate.call_count == 5
    assert result["success"] is False
    assert "module.py" in result["error"]
    assert not result.get("proposal_ids")
    assert (runtime.root_dir / "other.py").read_text(encoding="utf-8") == "value = 1\n"


def test_gemini_total_round_limit_also_withholds_unresolved_proposals(runtime):
    result, generate = run(runtime, [
        response(read()), response(invalid(), command()), response(text="Done."),
    ], rounds=3)
    assert generate.call_count == 3
    assert result["success"] is False
    assert "module.py" in result["error"]
    assert '"line": 2' in result["error"]
    assert not result.get("proposal_ids")


def test_gemini_returns_corrected_edit_without_unnecessary_extra_queries(runtime):
    result, generate = run(runtime, [
        response(read()), response(invalid()), response(corrected()), response(text="Ready to review."),
    ])
    assert generate.call_count == 4
    assert result["success"]
    assert len(result["proposal_ids"]) == 1
    assert runtime.apply_write(result["proposal_ids"][0]).ok
    assert (runtime.root_dir / "module.py").read_text(encoding="utf-8") == "def answer():\n    return 2\n"


def test_gemini_repeated_invalid_function_calls_stay_bounded(runtime):
    result, generate = run(runtime, [
        response(read()), response(invalid(), command()), response(invalid()), response(invalid()),
    ], rounds=4)
    assert generate.call_count == 4
    assert result["success"] is False
    assert "module.py" in result["error"]
    assert not result.get("proposal_ids")


def test_gemini_reports_unavailable_syntax_when_editing_an_unknown_language(runtime):
    (runtime.root_dir / "source.custom").write_text("before", encoding="utf-8")
    result, generate = run(runtime, [
        response(function("read_file", path="source.custom")),
        response(function("edit_file", path="source.custom", old_text="before", new_text="after")),
        response(text="Ready; syntax checking is unavailable for this file type."),
    ])
    assert generate.call_count == 3
    assert result["success"]
    assert result["syntax_warnings"][0]["path"] == "source.custom"
    assert result["syntax_warnings"][0]["syntax"]["status"] == "unavailable"


@pytest.mark.parametrize("tool", ["edit_file", "edit_file_ranges", "propose_edit_file", "propose_write_file"])
@pytest.mark.parametrize("new_text", ["return 3", "return ("])
def test_gemini_rejects_a_second_pending_edit_for_the_same_normalized_path(runtime, tool, new_text):
    digest = hashlib.sha256(SOURCE.encode("utf-8")).hexdigest()
    arguments = {
        "edit_file": {"old_text": "return 1", "new_text": new_text},
        "edit_file_ranges": {"edits": [{"start_line": 2, "end_line": 2, "new_text": "    " + new_text}]},
        "propose_edit_file": {"edits": [{"old_text": "return 1", "new_text": new_text}], "expected_sha256": digest},
        "propose_write_file": {"content": SOURCE.replace("return 1", new_text), "expected_sha256": digest},
    }[tool]
    duplicate = function(tool, path=" .\\module.py ", **arguments)
    with patch.object(runtime, "dispatch", wraps=runtime.dispatch) as dispatch:
        result, generate = run(runtime, [
            response(read()), response(corrected(), duplicate), response(text="Keep the original proposal."),
        ])

    assert generate.call_count == 3
    assert dispatch.call_count == 2  # The conflicting edit is rejected before evaluation.
    assert result["success"]
    assert len(result["proposal_ids"]) == 1
    assert len(runtime._proposals) == 1
    transcript = generate.call_args.kwargs["contents"]
    failures = [
        part.function_response.response for item in transcript for part in item.parts
        if part.function_response and part.function_response.response.get("error_code") == "PENDING_EDIT"
    ]
    assert len(failures) == 1
    assert (runtime.root_dir / "module.py").read_bytes() == SOURCE.encode("utf-8")
    assert runtime.apply_write(result["proposal_ids"][0]).ok
    assert (runtime.root_dir / "module.py").read_text(encoding="utf-8") == "def answer():\n    return 2\n"
