"""Behavioral coverage for atomic edits using original file line numbers."""

import codecs
import hashlib

import pytest

from core.range_edits import MAX_RANGE_EDITS, propose_line_edits
from core.tool_runtime import MAX_EDIT_FILE_BYTES, MAX_READ_BYTES, MAX_WRITE_BYTES, ToolRuntime


def source(tmp_path, content=b"alpha = 1\nbeta = 2\ngamma = 3\n", name="example.py"):
    path = tmp_path / name
    path.write_bytes(content)
    return ToolRuntime(str(tmp_path)), path


def region(start, end, replacement):
    return {"start_line": start, "end_line": end, "new_text": replacement}


def test_large_file_partial_read_and_distant_ranges_are_one_pending_change(tmp_path):
    lines = [f"value_{index} = {index}  # {'keep ' * 10}\n" for index in range(12000)]
    original = "".join(lines).encode()
    assert len(original) > MAX_READ_BYTES
    runtime, path = source(tmp_path, original)
    read = runtime.read_file(path.name, start_line=11000, end_line=11002)
    assert read.ok and read.data["total_lines"] == 12000
    result = runtime.edit_file_ranges(path.name, [
        region(12000, 12000, "last_value = 42"),
        region(11000, 11001, "selected_value = 10\nselected_value += 1"),
    ], "Update two distant regions")
    assert result.ok, result.as_dict()
    assert result.data["status"] == "pending"
    assert result.data["edit_count"] == 2
    assert len(runtime._proposals) == 1
    assert path.read_bytes() == original
    assert runtime.apply_write(result.data["proposal_id"]).ok
    expected = lines[:10999] + ["selected_value = 10\n", "selected_value += 1\n"] + lines[11001:11999] + ["last_value = 42\n"]
    assert path.read_bytes() == "".join(expected).encode()


def test_replace_delete_and_insert_use_original_coordinates_in_any_input_order(tmp_path):
    original = b"# heading\na = 1\nb = 2\nc = 3\n# tail\n"
    runtime, path = source(tmp_path, original)
    assert runtime.read_file(path.name).ok
    result = runtime.edit_file_ranges(path.name, [
        region(4, 4, "c = 30\nnew_value = 40"),
        region(6, 5, "# appended\n"),
        region(2, 2, ""),
        region(1, 0, "# inserted"),
    ])
    assert result.ok, result.as_dict()
    assert result.data["original_lines"] == 5
    assert path.read_bytes() == original
    assert runtime.apply_write(result.data["proposal_id"]).ok
    assert path.read_bytes() == b"# inserted\n# heading\nb = 2\nc = 30\nnew_value = 40\n# tail\n# appended\n"


@pytest.mark.parametrize("bom", [b"", codecs.BOM_UTF8])
def test_bom_and_crlf_survive_multiline_replacement_and_insertion(tmp_path, bom):
    original = bom + "# tiếng Việt\r\nalpha = 1\r\nbeta = 2\r\n".encode()
    runtime, path = source(tmp_path, original)
    assert runtime.read_file(path.name).ok
    result = runtime.edit_file_ranges(path.name, [
        region(2, 2, "alpha = 3\nextra = 4"),
        region(3, 2, "# new comment"),
    ])
    assert result.ok, result.as_dict()
    assert runtime.apply_write(result.data["proposal_id"]).ok
    assert path.read_bytes() == bom + "# tiếng Việt\r\nalpha = 3\r\nextra = 4\r\n# new comment\r\nbeta = 2\r\n".encode()


@pytest.mark.parametrize("original,replacement,expected", [
    (b"alpha = 1", "beta = 2", b"alpha = 1\nbeta = 2"),
    (b"alpha = 1\n", "beta = 2", b"alpha = 1\nbeta = 2"),
    (b"", "beta = 2\n", b"beta = 2\n"),
])
def test_eof_and_empty_file_insertions_do_not_join_source_lines(tmp_path, original, replacement, expected):
    runtime, path = source(tmp_path, original)
    assert runtime.read_file(path.name).ok
    total = len(original.splitlines())
    result = runtime.edit_file_ranges(path.name, [region(total + 1, total, replacement)])
    assert result.ok, result.as_dict()
    assert runtime.apply_write(result.data["proposal_id"]).ok
    assert path.read_bytes() == expected


def test_whole_file_can_be_replaced_without_resending_old_text(tmp_path):
    runtime, path = source(tmp_path)
    assert runtime.read_file(path.name).ok
    result = runtime.edit_file_ranges(path.name, [region(1, 3, "answer = 42")])
    assert result.ok, result.as_dict()
    assert runtime.apply_write(result.data["proposal_id"]).ok
    assert path.read_bytes() == b"answer = 42\n"


def test_read_is_required_before_using_line_numbers(tmp_path):
    runtime, path = source(tmp_path)
    result = runtime.edit_file_ranges(path.name, [region(1, 1, "alpha = 4")])
    assert not result.ok and result.error_code == "READ_REQUIRED"
    assert not runtime._proposals


@pytest.mark.parametrize("when", ["before_proposal", "before_apply", "during_proposal"])
def test_stale_snapshot_never_overwrites_independent_changes(tmp_path, monkeypatch, when):
    runtime, path = source(tmp_path)
    assert runtime.read_file(path.name).ok
    changed = b"# independently edited\nalpha = 10\n"
    if when == "before_proposal":
        path.write_bytes(changed)
    elif when == "during_proposal":
        original_propose = runtime.propose_write_file

        def race(*args, **kwargs):
            path.write_bytes(changed)
            return original_propose(*args, **kwargs)

        monkeypatch.setattr(runtime, "propose_write_file", race)
    result = runtime.edit_file_ranges(path.name, [region(1, 1, "alpha = 4")])
    if when == "before_apply":
        assert result.ok
        path.write_bytes(changed)
        result = runtime.apply_write(result.data["proposal_id"])
    else:
        assert not runtime._proposals
        assert runtime.edit_file_ranges(path.name, [region(1, 1, "alpha = 4")]).error_code == "READ_REQUIRED"
    assert not result.ok and result.error_code == "STALE_CONTENT"
    assert path.read_bytes() == changed


@pytest.mark.parametrize("edits", [
    [region(1, 2, "x = 1"), region(2, 3, "y = 2")],
    [region(1, 3, "x = 1"), region(2, 1, "y = 2")],
    [region(2, 1, "x = 1"), region(2, 1, "y = 2")],
])
def test_overlapping_replacements_and_ambiguous_insertions_are_atomic_failures(tmp_path, edits):
    runtime, path = source(tmp_path)
    original = path.read_bytes()
    assert runtime.read_file(path.name).ok
    result = runtime.edit_file_ranges(path.name, edits)
    assert not result.ok and result.error_code == "OVERLAPPING_EDITS"
    assert not runtime._proposals
    assert path.read_bytes() == original


@pytest.mark.parametrize("edits,error", [
    ([], "INVALID_EDITS"),
    ([region(1, 1, "alpha = 4")] * (MAX_RANGE_EDITS + 1), "INVALID_EDITS"),
    ([region(0, 0, "alpha = 4")], "INVALID_RANGE"),
    ([region(4, 4, "alpha = 4")], "INVALID_RANGE"),
    ([region(2, 0, "alpha = 4")], "INVALID_RANGE"),
    ([region(True, 1, "alpha = 4")], "INVALID_EDITS"),
    ([region(1, 1, None)], "INVALID_EDITS"),
    ([region(1, 1, "\x00")], "INVALID_EDITS"),
    ([dict(region(1, 1, "alpha = 4"), replace_all=True)], "INVALID_EDITS"),
    ([region(1, 1, "alpha = 1")], "NO_CHANGE"),
])
def test_invalid_ranges_and_noop_changes_leave_file_untouched(tmp_path, edits, error):
    runtime, path = source(tmp_path)
    original = path.read_bytes()
    assert runtime.read_file(path.name).ok
    result = runtime.edit_file_ranges(path.name, edits)
    assert not result.ok and result.error_code == error
    assert not runtime._proposals
    assert path.read_bytes() == original


def test_oversized_input_is_rejected_even_without_runtime_read(tmp_path):
    original = b"#" + b"x" * MAX_EDIT_FILE_BYTES
    runtime, path = source(tmp_path, original)
    result = propose_line_edits(runtime, path.name, [region(1, 1, "# small")], hashlib.sha256(original).hexdigest())
    assert not result.ok and result.error_code == "TOO_LARGE"
    assert not runtime._proposals
    assert path.read_bytes() == original


def test_oversized_result_is_rejected_before_a_proposal_is_created(tmp_path):
    runtime, path = source(tmp_path)
    original = path.read_bytes()
    assert runtime.read_file(path.name).ok
    result = runtime.edit_file_ranges(path.name, [region(1, 1, "#" + "x" * MAX_WRITE_BYTES)])
    assert not result.ok and result.error_code == "TOO_LARGE"
    assert not runtime._proposals
    assert path.read_bytes() == original


def test_invalid_syntax_reports_location_and_keeps_original_for_corrected_retry(tmp_path):
    runtime, path = source(tmp_path)
    original = path.read_bytes()
    assert runtime.read_file(path.name).ok
    failed = runtime.edit_file_ranges(path.name, [region(2, 2, "def broken(:")])
    assert not failed.ok and failed.error_code == "SYNTAX_ERROR"
    report = failed.as_dict()["syntax"]
    assert report["status"] == "invalid"
    assert report["language"] == "python"
    assert report["diagnostics"][0]["line"] == 2
    assert not runtime._proposals
    assert path.read_bytes() == original
    fixed = runtime.edit_file_ranges(path.name, [region(2, 2, "beta = 20")])
    assert fixed.ok and fixed.data["syntax"]["status"] == "valid"
    assert runtime.apply_write(fixed.data["proposal_id"]).ok
    assert path.read_bytes() == original.replace(b"beta = 2", b"beta = 20")


def test_invalid_description_returns_a_structured_error(tmp_path):
    runtime, path = source(tmp_path)
    assert runtime.read_file(path.name).ok
    result = runtime.edit_file_ranges(path.name, [region(1, 1, "alpha = 4")], description=None)
    assert not result.ok and result.error_code == "INVALID_ARGUMENTS"
    assert not runtime._proposals


@pytest.mark.parametrize("path,error", [("../outside.py", "PATH_OUTSIDE"), (".env", "SENSITIVE_FILE"), (".git/config", "PATH_DENIED")])
def test_workspace_and_sensitive_file_policies_also_apply_to_line_edits(tmp_path, path, error):
    runtime, _ = source(tmp_path)
    result = runtime.edit_file_ranges(path, [region(1, 1, "alpha = 4")])
    assert not result.ok and result.error_code == error
    assert not runtime._proposals


def test_dispatch_accepts_line_ranges_without_model_supplied_hash(tmp_path):
    runtime, path = source(tmp_path)
    assert runtime.dispatch("read_file", {"path": path.name})["ok"]
    result = runtime.dispatch("edit_file_ranges", {"path": path.name, "edits": [region(1, 1, "alpha = 4")]})
    assert result["ok"] and result["status"] == "pending"
    assert path.read_bytes().startswith(b"alpha = 1\n")
