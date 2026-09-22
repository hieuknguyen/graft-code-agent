"""The simple edit tool uses observed source versions instead of model hashes."""

import codecs
from unittest.mock import patch

import pytest

from core.gemini_agent import GeminiCodingAgent
from core.tool_runtime import ToolRuntime


@pytest.fixture
def runtime(tmp_path):
    (tmp_path / "example.py").write_bytes(b"value = 1\n# untouched\n")
    return ToolRuntime(str(tmp_path))


def edit(runtime, **kwargs):
    return runtime.edit_file("example.py", "value = 1", "value = 2", **kwargs)


def test_edit_requires_prior_read_and_never_writes_immediately(runtime):
    assert edit(runtime).error_code == "READ_REQUIRED"
    assert runtime.read_file("example.py").ok
    result = edit(runtime, description="Update value")
    assert result.ok and result.data["status"] == "pending"
    target = runtime.root_dir / "example.py"
    assert target.read_bytes() == b"value = 1\n# untouched\n"
    assert runtime.apply_write(result.data["proposal_id"]).ok
    assert target.read_bytes() == b"value = 2\n# untouched\n"


@pytest.mark.parametrize("change", ["modify", "delete"])
def test_stale_edit_invalidates_read_version(runtime, change):
    runtime.read_file("example.py")
    target = runtime.root_dir / "example.py"
    if change == "modify":
        target.write_bytes(b"value = 1\n# edited independently\n")
    else:
        target.unlink()
    assert edit(runtime).error_code == "STALE_CONTENT"
    target.write_bytes(b"value = 1\n# edited independently\n")
    assert edit(runtime).error_code == "READ_REQUIRED"
    assert runtime.read_file("example.py").ok
    assert edit(runtime).ok


def test_failed_or_empty_reread_does_not_authorize_edit(runtime):
    runtime.read_file("example.py")
    assert not runtime.read_file("example.py", start_line="invalid").ok
    assert edit(runtime).error_code == "READ_REQUIRED"
    assert runtime.read_file("example.py", start_line=100).ok
    assert edit(runtime).error_code == "READ_REQUIRED"


def test_partial_read_and_path_alias_use_the_same_version(runtime):
    assert runtime.read_file("./example.py", start_line=1, end_line=1).ok
    assert runtime.edit_file(" example.py ", "value = 1", "value = 2").ok


def test_ambiguous_text_returns_error_without_change(runtime):
    target = runtime.root_dir / "example.py"
    target.write_bytes(b"value = 1\nvalue = 1\n")
    runtime.read_file("example.py")
    assert edit(runtime).error_code == "AMBIGUOUS_EDIT"
    assert not runtime._proposals
    assert target.read_bytes() == b"value = 1\nvalue = 1\n"


def test_edit_retains_bom_and_crlf_without_hash_from_model(runtime):
    target = runtime.root_dir / "example.py"
    raw = codecs.BOM_UTF8 + b"value = 1\r\n# untouched\r\n"
    target.write_bytes(raw)
    runtime.read_file("example.py")
    result = runtime.edit_file("example.py", "value = 1\n# untouched", "value = 2\n# untouched")
    assert result.ok
    assert runtime.apply_write(result.data["proposal_id"]).ok
    assert target.read_bytes() == raw.replace(b"value = 1", b"value = 2")


def test_read_symbol_remembers_source_for_simple_edit(runtime):
    (runtime.root_dir / "example.py").write_bytes(b"def answer():\n    return 1\n")
    assert runtime.read_symbol("example.py", "answer").ok
    assert runtime.edit_file("example.py", "return 1", "return 2").ok


def test_failed_symbol_read_does_not_remember_unseen_changed_source(runtime):
    target = runtime.root_dir / "example.py"
    target.write_bytes(b"def answer():\n    return 1\n")
    read = runtime.read_file

    def changed_read(*args, **kwargs):
        target.write_bytes(b"def answer():\n    return 3\n")
        return read(*args, **kwargs)

    with patch.object(runtime, "read_file", side_effect=changed_read):
        assert runtime.read_symbol("example.py", "answer").error_code == "STALE_CONTENT"
    assert runtime.edit_file("example.py", "return 3", "return 4").error_code == "READ_REQUIRED"


@pytest.mark.parametrize("path, code", [("../outside.py", "PATH_OUTSIDE"), (".env", "SENSITIVE_FILE")])
def test_edit_reuses_workspace_boundary(runtime, path, code):
    assert runtime.edit_file(path, "a", "b").error_code == code


def test_dispatch_and_gemini_schema_expose_simple_arguments(runtime):
    runtime.dispatch("read_file", {"path": "example.py"})
    result = runtime.dispatch("edit_file", {"path": "example.py", "old_text": "value = 1", "new_text": "value = 2"})
    assert result["ok"]
    schema = next(item["parameters_json_schema"] for item in GeminiCodingAgent._tool_schemas() if item["name"] == "edit_file")
    assert set(schema["required"]) == {"path", "old_text", "new_text"}
    assert "expected_sha256" not in schema["properties"]
