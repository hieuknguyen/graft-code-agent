import codecs
import hashlib
from pathlib import Path

import pytest

from core.edit_tools import MAX_EDITS, propose_edit_file
from core.tool_runtime import MAX_EDIT_FILE_BYTES, MAX_WRITE_BYTES, ToolRuntime


def _source(tmp_path, content=b"alpha = 1\nbeta = 2\n"):
    path = tmp_path / "example.py"
    path.write_bytes(content)
    return ToolRuntime(str(tmp_path)), path, hashlib.sha256(content).hexdigest()


def test_multiple_edits_are_pending_until_applied_and_preserve_other_content(tmp_path):
    original = b"# keep\nalpha = 1\nbeta = 2\n# tail without newline"
    runtime, path, source_hash = _source(tmp_path, original)
    result = propose_edit_file(runtime, path.name, [
        {"old_text": "beta = 2", "new_text": "beta = 20"},
        {"old_text": "alpha = 1", "new_text": "alpha = 10"},
    ], source_hash, "Update values")

    assert result.ok
    assert result.data["edit_count"] == 2
    assert result.data["original_sha256"] == source_hash
    assert path.read_bytes() == original
    proposal_id = result.data["proposal_id"]
    proposal = runtime.proposal_for_ui(proposal_id)
    assert proposal.ok and proposal.data["kind"] == "write"
    assert proposal.data["description"] == "Update values"
    assert runtime._proposals[proposal_id].payload["original_sha256"] == source_hash
    assert runtime.apply_write(proposal_id).ok
    assert path.read_bytes() == b"# keep\nalpha = 10\nbeta = 20\n# tail without newline"
    assert not runtime.apply_write(proposal_id).ok


@pytest.mark.parametrize("bom", [b"", codecs.BOM_UTF8])
def test_apply_preserves_utf8_bom_and_exact_line_endings(tmp_path, bom):
    original = bom + "# tiếng Việt\r\nalpha = 1\r\nbeta = 2\nlast".encode("utf-8")
    runtime, path, source_hash = _source(tmp_path, original)
    result = propose_edit_file(runtime, path.name, [
        {"old_text": "alpha = 1\r\nbeta = 2", "new_text": "alpha = 3\r\nbeta = 4"},
    ], source_hash)
    assert result.ok
    assert runtime.apply_write(result.data["proposal_id"]).ok
    assert path.read_bytes() == bom + "# tiếng Việt\r\nalpha = 3\r\nbeta = 4\nlast".encode("utf-8")


def test_edit_supports_deleting_exact_text(tmp_path):
    runtime, path, source_hash = _source(tmp_path)
    result = propose_edit_file(runtime, path.name, [{"old_text": "alpha = 1\n", "new_text": ""}], source_hash)
    assert result.ok
    assert runtime.apply_write(result.data["proposal_id"]).ok
    assert path.read_bytes() == b"beta = 2\n"


@pytest.mark.parametrize("bom", [b"", codecs.BOM_UTF8])
def test_lf_edit_strings_follow_consistent_crlf_source_style(tmp_path, bom):
    original = bom + b"# keep\r\nalpha = 1\r\nbeta = 2\r\n# tail\r\n"
    runtime, path, source_hash = _source(tmp_path, original)
    result = propose_edit_file(runtime, path.name, [
        {"old_text": "alpha = 1\nbeta = 2", "new_text": "alpha = 3\nbeta = 4"},
    ], source_hash)
    assert result.ok and result.data["newline_handling"] == "normalized_to_crlf"
    assert path.read_bytes() == original
    assert runtime.apply_write(result.data["proposal_id"]).ok
    assert path.read_bytes() == bom + b"# keep\r\nalpha = 3\r\nbeta = 4\r\n# tail\r\n"


def test_newline_normalization_does_not_create_noop_proposal(tmp_path):
    runtime, path, source_hash = _source(tmp_path, b"alpha\r\nbeta\r\n")
    result = propose_edit_file(runtime, path.name, [
        {"old_text": "alpha\nbeta", "new_text": "alpha\r\nbeta"},
    ], source_hash)
    assert not result.ok and result.error_code == "NO_CHANGE"
    assert not runtime._proposals


@pytest.mark.parametrize("when", ["before_proposal", "before_apply", "during_delegate"])
def test_stale_snapshot_never_overwrites_new_content(tmp_path, monkeypatch, when):
    runtime, path, source_hash = _source(tmp_path)
    newer = b"changed independently\n"
    if when == "before_proposal":
        path.write_bytes(newer)
    elif when == "during_delegate":
        original_propose = runtime.propose_write_file

        def concurrent_propose(**kwargs):
            path.write_bytes(newer)
            return original_propose(**kwargs)

        monkeypatch.setattr(runtime, "propose_write_file", concurrent_propose)
    result = propose_edit_file(runtime, path.name, [{"old_text": "alpha = 1", "new_text": "alpha = 3"}], source_hash)
    if when == "before_apply":
        assert result.ok
        path.write_bytes(newer)
        result = runtime.apply_write(result.data["proposal_id"])
    else:
        assert not runtime._proposals
    assert not result.ok and result.error_code == "STALE_CONTENT"
    assert path.read_bytes() == newer


@pytest.mark.parametrize(("source", "edits", "error"), [
    (b"alpha alpha", [{"old_text": "alpha", "new_text": "beta"}], "AMBIGUOUS_EDIT"),
    (b"aaa", [{"old_text": "aa", "new_text": "b"}], "AMBIGUOUS_EDIT"),
    (b"abcdef", [{"old_text": "abc", "new_text": "x"}, {"old_text": "cde", "new_text": "y"}], "OVERLAPPING_EDITS"),
    (b"abcdef", [{"old_text": "abc", "new_text": "x"}, {"old_text": "abc", "new_text": "y"}], "OVERLAPPING_EDITS"),
    (b"alpha", [{"old_text": "beta", "new_text": "x"}], "EDIT_NOT_FOUND"),
    (b"alpha", [{"old_text": "alpha", "new_text": "beta"}, {"old_text": "beta", "new_text": "gamma"}], "EDIT_NOT_FOUND"),
    (b"alpha\r\nbeta\n", [{"old_text": "alpha\nbeta", "new_text": "x"}], "EDIT_NOT_FOUND"),
    (b"alpha", [{"old_text": "alpha", "new_text": "alpha"}], "NO_CHANGE"),
    (b"ab", [{"old_text": "a", "new_text": "ab"}, {"old_text": "b", "new_text": ""}], "NO_CHANGE"),
])
def test_rejects_missing_ambiguous_overlapping_and_noop_edits(tmp_path, source, edits, error):
    runtime, path, source_hash = _source(tmp_path, source)
    result = propose_edit_file(runtime, path.name, edits, source_hash)
    assert not result.ok and result.error_code == error
    assert path.read_bytes() == source
    assert not runtime._proposals


def test_matching_uses_original_snapshot_even_when_replacements_introduce_matches(tmp_path):
    runtime, path, source_hash = _source(tmp_path, b"alpha + beta")
    result = propose_edit_file(runtime, path.name, [
        {"old_text": "alpha", "new_text": "beta"},
        {"old_text": "beta", "new_text": "gamma"},
    ], source_hash)
    assert result.ok and runtime.apply_write(result.data["proposal_id"]).ok
    assert path.read_bytes() == b"beta + gamma"


@pytest.mark.parametrize("edits", [None, {}, "text", [], [None], [{}],
    [{"old_text": "", "new_text": "x"}], [{"old_text": 1, "new_text": "x"}],
    [{"old_text": "alpha", "new_text": None}],
    [{"old_text": "alpha", "new_text": "x", "replace_all": True}],
    [{"old_text": "alpha", "new_text": "\x00"}],
    [{"old_text": "\x00", "new_text": "alpha"}],
    [{"old_text": "alpha", "new_text": "beta"}] * (MAX_EDITS + 1),
])
def test_rejects_invalid_edits(tmp_path, edits):
    runtime, path, source_hash = _source(tmp_path)
    result = propose_edit_file(runtime, path.name, edits, source_hash)
    assert not result.ok and result.error_code == "INVALID_EDITS"
    assert not runtime._proposals


@pytest.mark.parametrize("expected_hash", [None, "", "abc", "z" * 64, 42])
def test_requires_valid_source_hash(tmp_path, expected_hash):
    runtime, path, _ = _source(tmp_path)
    result = propose_edit_file(runtime, path.name, [{"old_text": "alpha", "new_text": "beta"}], expected_hash)
    assert not result.ok and result.error_code == "INVALID_HASH"
    assert not runtime._proposals


@pytest.mark.parametrize(("path", "error"), [
    ("../outside.py", "PATH_OUTSIDE"), ("C:/outside.py", "PATH_OUTSIDE"),
    (".git/config", "PATH_DENIED"), (".env", "SENSITIVE_FILE"),
    ("secret.key", "SENSITIVE_FILE"), ("missing.py", "NOT_FOUND"),
    ("", "INVALID_PATH"), (None, "INVALID_PATH"),
])
def test_rejects_unsafe_or_invalid_paths_before_reading(tmp_path, monkeypatch, path, error):
    runtime, _, source_hash = _source(tmp_path)

    def forbidden_read(*args, **kwargs):
        pytest.fail("The denied path must not be opened")

    monkeypatch.setattr(Path, "open", forbidden_read)
    result = propose_edit_file(runtime, path, [{"old_text": "alpha", "new_text": "beta"}], source_hash)
    assert not result.ok and result.error_code == error
    assert not runtime._proposals


def test_invalid_description_returns_structured_error(tmp_path):
    runtime, path, source_hash = _source(tmp_path)
    result = propose_edit_file(runtime, path.name, [{"old_text": "alpha", "new_text": "beta"}], source_hash, None)
    assert not result.ok and result.error_code == "INVALID_ARGUMENTS"
    assert not runtime._proposals


@pytest.mark.parametrize(("target", "error"), [(".env", "SENSITIVE_FILE"), (".git/config", "PATH_DENIED")])
def test_rejects_resolved_alias_to_sensitive_or_ignored_file(tmp_path, monkeypatch, target, error):
    runtime, _, source_hash = _source(tmp_path)
    # Model the canonical path returned for an in-project filesystem alias.
    monkeypatch.setattr(runtime.policy, "resolve_read_path", lambda path: (tmp_path / target, Path(path)))

    def forbidden_read(*args, **kwargs):
        pytest.fail("The resolved denied target must not be opened")

    monkeypatch.setattr(Path, "open", forbidden_read)
    result = propose_edit_file(runtime, "alias.py", [{"old_text": "alpha", "new_text": "beta"}], source_hash)
    assert not result.ok and result.error_code == error
    assert not runtime._proposals


def test_rejects_oversized_final_content_even_when_edit_input_fits(tmp_path):
    runtime, path, source_hash = _source(tmp_path, b"alpha\n" + b"x" * 100)
    result = propose_edit_file(runtime, path.name, [
        {"old_text": "alpha", "new_text": "y" * (MAX_WRITE_BYTES - 5)},
    ], source_hash)
    assert not result.ok and result.error_code == "TOO_LARGE"
    assert not runtime._proposals


@pytest.mark.parametrize(("source", "error"), [
    (b"alpha\x00", "BINARY"), (b"x" * 8192 + b"\x00alpha", "BINARY"),
    (b"alpha\xff", "INVALID_ENCODING"), (b"alpha" * (MAX_EDIT_FILE_BYTES // 5 + 1), "TOO_LARGE"),
], ids=["nul", "late-nul", "invalid-utf8", "too-large"])
def test_rejects_binary_non_utf8_and_oversized_files(tmp_path, source, error):
    runtime, path, source_hash = _source(tmp_path, source)
    result = propose_edit_file(runtime, path.name, [{"old_text": "alpha", "new_text": "beta"}], source_hash)
    assert not result.ok and result.error_code == error
    assert not runtime._proposals


@pytest.mark.parametrize(("replacement", "error"), [("x" * MAX_WRITE_BYTES, "TOO_LARGE"), ("\ud800", "INVALID_ENCODING")], ids=["too-large", "invalid-utf8"])
def test_rejects_oversized_or_invalid_utf8_replacements(tmp_path, replacement, error):
    runtime, path, source_hash = _source(tmp_path)
    result = propose_edit_file(runtime, path.name, [{"old_text": "alpha", "new_text": replacement}], source_hash)
    assert not result.ok and result.error_code == error
    assert not runtime._proposals
