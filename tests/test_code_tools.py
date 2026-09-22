import hashlib
import json

import pytest

from core.code_tools import CodeTools, MAX_SYMBOLS
from core.tool_runtime import MAX_EDIT_FILE_BYTES, MAX_READ_BYTES, MAX_READ_CHARS, MAX_READ_LINES, ToolRuntime


@pytest.fixture
def code_tools(tmp_path):
    return CodeTools(ToolRuntime(str(tmp_path)))


def write_source(root, path, source):
    destination = root / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(source, encoding="utf-8")
    return destination


def test_find_files_recursive_glob_includes_root_and_pages_exactly(tmp_path, code_tools):
    for path in ("main.py", "src/alpha.py", "src/nested/beta.py", "src/main.js"):
        write_source(tmp_path, path, "pass\n")
    for path in (".git/hidden.py", "node_modules/package/hidden.py", ".env", "src/private.key"):
        write_source(tmp_path, path, "private")

    first = code_tools.find_files("**/*.py", max_results=2)
    assert first.ok
    assert [row["path"] for row in first.data["files"]] == ["main.py", "src/alpha.py"]
    assert first.data["total_matches"] == 3
    assert first.data["total_matches_is_exact"] is True
    assert first.data["next_offset"] == 2
    assert first.data["truncated"] is True
    last = code_tools.find_files("**/*.py", max_results=2, offset=2)
    assert [row["path"] for row in last.data["files"]] == ["src/nested/beta.py"]
    assert last.data["next_offset"] is None
    assert last.data["truncated"] is False
    all_paths = {row["path"] for row in code_tools.find_files("*").data["files"]}
    assert all_paths == {"main.py", "src/alpha.py", "src/nested/beta.py", "src/main.js"}


def test_find_files_directory_globs_do_not_cross_single_star(tmp_path, code_tools):
    for path in ("root.py", "src/direct.py", "src/deep/indirect.py"):
        write_source(tmp_path, path, "pass")
    assert [row["path"] for row in code_tools.find_files("src/*.py").data["files"]] == ["src/direct.py"]
    assert len(code_tools.find_files("*.py").data["files"]) == 3
    assert len(code_tools.find_files("src/**/*.py").data["files"]) == 2


@pytest.mark.parametrize("pattern, code", [
    ("../*.py", "PATH_OUTSIDE"), ("C:/outside/*.py", "PATH_OUTSIDE"),
    ("/outside/*.py", "PATH_OUTSIDE"), (".git/*", "PATH_DENIED"),
    ("", "INVALID_PATTERN"), (None, "INVALID_PATTERN"),
])
def test_find_files_rejects_invalid_or_unsafe_patterns(code_tools, pattern, code):
    result = code_tools.find_files(pattern)
    assert not result.ok
    assert result.error_code == code


def test_find_files_scan_limit_is_distinguished_from_pagination(tmp_path, code_tools, monkeypatch):
    for name in ("a.py", "b.py", "c.py"):
        write_source(tmp_path, name, "pass")
    monkeypatch.setattr("core.code_tools.MAX_SEARCH_FILES", 2)
    result = code_tools.find_files("*.py")
    assert result.ok
    assert result.data["scanned_files"] == 2
    assert result.data["returned_count"] == 2
    assert result.data["scan_truncated"] is True
    assert result.data["total_matches_is_exact"] is False
    assert result.data["next_offset"] is None
    assert result.data["truncated"] is True


def test_find_files_character_limit_keeps_pagination_progress(tmp_path, code_tools, monkeypatch):
    for name in ("alpha.py", "bravo.py", "charlie.py"):
        write_source(tmp_path, name, "pass")
    monkeypatch.setattr("core.code_tools.MAX_READ_CHARS", 50)
    first = code_tools.find_files("*.py")
    assert first.data["returned_count"] == 1
    assert first.data["next_offset"] == 1
    assert first.data["truncated"] is True
    next_page = code_tools.find_files("*.py", offset=first.data["next_offset"])
    assert next_page.data["files"][0]["path"] == "bravo.py"


@pytest.mark.parametrize("kwargs", [{"offset": -1}, {"offset": "wrong"}, {"max_results": None}])
def test_find_files_reports_bad_pagination(code_tools, kwargs):
    result = code_tools.find_files("*", **kwargs)
    assert not result.ok
    assert result.error_code == "INVALID_RANGE"


DECORATED_SOURCE = """@decorate
class Service:
    @staticmethod
    @(
        decorate
    )
    def run(value):
        password = "hidden-password"
        return value

class Worker:
    async def run(self):
        return 2

def outer():
    def inner():
        return 3
    return inner()
"""


def test_list_symbols_preserves_decorators_ranges_and_nested_parents(tmp_path, code_tools):
    source_file = write_source(tmp_path, "module.py", DECORATED_SOURCE)
    result = code_tools.list_symbols("module.py")
    assert result.ok
    assert result.data["sha256"] == hashlib.sha256(source_file.read_bytes()).hexdigest()
    rows = {row["qualified_name"]: row for row in result.data["symbols"]}
    assert (rows["Service"]["start_line"], rows["Service"]["end_line"]) == (1, 9)
    assert (rows["Service.run"]["start_line"], rows["Service.run"]["end_line"]) == (3, 9)
    assert rows["Service.run"]["type"] == "method"
    assert rows["outer.inner"]["type"] == "function"
    assert rows["outer.inner"]["parent"] == "outer"
    assert result.data["total_symbols"] == 6
    assert result.data["truncated"] is False
    assert "hidden-password" not in json.dumps(result.as_dict())


def test_parenthesised_decorator_includes_its_at_line(tmp_path, code_tools):
    write_source(tmp_path, "decorators.py", "@(\n    decorate\n)\ndef work():\n    return 1\n")
    result = code_tools.read_symbol("decorators.py", "work")
    assert result.ok
    assert result.data["start_line"] == 1
    assert result.data["content"].startswith("    1 | @(")


def test_read_symbol_disambiguates_methods_and_redacts_source(tmp_path, code_tools):
    write_source(tmp_path, "module.py", DECORATED_SOURCE)
    ambiguous = code_tools.read_symbol("module.py", "run")
    assert ambiguous.error_code == "AMBIGUOUS_SYMBOL"
    assert "Service.run" in ambiguous.error
    assert "Worker.run" in ambiguous.error
    selected = code_tools.read_symbol("module.py", "run", parent="Service")
    assert selected.ok
    assert selected.data["start_line"] == 3
    assert selected.data["end_line"] == 9
    assert "@staticmethod" in selected.data["content"]
    assert "[REDACTED]" in selected.data["content"]
    assert "hidden-password" not in selected.data["content"]
    assert "class Worker" not in selected.data["content"]
    assert selected.data["truncated"] is False
    qualified = code_tools.read_symbol("module.py", "Service.run")
    assert qualified.data["content"] == selected.data["content"]
    assert code_tools.read_symbol("module.py", "missing").error_code == "SYMBOL_NOT_FOUND"


def test_duplicate_definitions_remain_ambiguous_even_with_parent(tmp_path, code_tools):
    write_source(tmp_path, "duplicate.py", "class A:\n    def run(self): pass\n    def run(self): pass\n")
    result = code_tools.read_symbol("duplicate.py", "run", parent="A")
    assert result.error_code == "AMBIGUOUS_SYMBOL"


def test_symbols_accept_stubs_and_valid_files_without_definitions(tmp_path, code_tools):
    write_source(tmp_path, "api.pyi", "def call(value: str) -> int: ...\n")
    assert code_tools.read_symbol("api.pyi", "call").ok
    write_source(tmp_path, "constants.py", "VALUE = 42\n")
    result = code_tools.list_symbols("constants.py")
    assert result.ok
    assert result.data["symbols"] == []
    assert result.data["total_symbols"] == 0


def test_symbol_limit_and_long_symbol_are_explicitly_truncated(tmp_path, code_tools):
    write_source(tmp_path, "many.py", "\n".join(f"def f{i}(): pass" for i in range(MAX_SYMBOLS + 1)))
    listed = code_tools.list_symbols("many.py")
    assert listed.data["total_symbols"] == MAX_SYMBOLS + 1
    assert len(listed.data["symbols"]) == MAX_SYMBOLS
    assert listed.data["truncated"] is True
    write_source(tmp_path, "long.py", "def long():\n" + "    pass\n" * MAX_READ_LINES)
    result = code_tools.read_symbol("long.py", "long")
    assert result.ok
    assert result.data["end_line"] == MAX_READ_LINES
    assert result.data["symbol"]["end_line"] == MAX_READ_LINES + 1
    assert result.data["truncated"] is True
    write_source(tmp_path, "wide.py", "def wide():\n    return '" + "x" * (MAX_READ_CHARS + 10) + "'\n")
    wide = code_tools.read_symbol("wide.py", "wide")
    assert wide.ok
    assert wide.data["truncated"] is True
    assert len(wide.data["content"]) < MAX_READ_CHARS + 100


def test_read_symbol_detects_source_changed_between_parsing_and_read(tmp_path, code_tools, monkeypatch):
    source_file = write_source(tmp_path, "changing.py", "def work():\n    return 1\n")
    read_file = code_tools.runtime.read_file

    def change_then_read(*args, **kwargs):
        source_file.write_text("def work():\n    return 999\n", encoding="utf-8")
        return read_file(*args, **kwargs)

    monkeypatch.setattr(code_tools.runtime, "read_file", change_then_read)
    assert code_tools.read_symbol("changing.py", "work").error_code == "STALE_CONTENT"


@pytest.mark.parametrize("method", ["list_symbols", "read_symbol", "check_syntax"])
@pytest.mark.parametrize("path, expected", [
    ("missing.py", "NOT_FOUND"), ("../outside.py", "PATH_OUTSIDE"),
    (".git/internal.py", "PATH_DENIED"), (".env", "SENSITIVE_FILE"),
])
def test_inspection_tools_share_workspace_policy(code_tools, method, path, expected):
    args = (path, "work") if method == "read_symbol" else (path,)
    result = getattr(code_tools, method)(*args)
    assert not result.ok
    assert result.error_code == expected


def test_unsupported_languages_and_invalid_python_are_explicit(tmp_path, code_tools):
    write_source(tmp_path, "module.js", "function work() { return 1; }")
    for method, args in (("list_symbols", ("module.js",)), ("read_symbol", ("module.js", "work"))):
        result = getattr(code_tools, method)(*args)
        assert result.error_code == "UNSUPPORTED_LANGUAGE"
    write_source(tmp_path, "unknown.custom", "custom language")
    unchecked = code_tools.check_syntax("unknown.custom")
    assert unchecked.ok
    assert unchecked.data["status"] == "unavailable"
    assert unchecked.data["valid"] is None
    write_source(tmp_path, "broken.py", "def invalid(:\n")
    assert code_tools.list_symbols("broken.py").error_code == "SYNTAX_ERROR"
    assert code_tools.read_symbol("broken.py", "invalid").error_code == "SYNTAX_ERROR"


@pytest.mark.parametrize("source", ["def broken(:\n", "return 1\n", "break\n", "await work()\n"])
def test_python_syntax_checks_include_context_errors(tmp_path, code_tools, source):
    write_source(tmp_path, "broken.py", source)
    result = code_tools.check_syntax("broken.py")
    assert result.ok
    assert result.data["valid"] is False
    assert result.data["diagnostics"][0]["line"] == 1
    assert result.data["diagnostics"][0]["message"]


@pytest.mark.parametrize("content, valid", [
    ('{"enabled": true, "items": [1, null]}', True),
    ('{"broken": }', False), ('{"value": NaN}', False), ('{"value": Infinity}', False),
])
def test_json_syntax_uses_strict_json(tmp_path, code_tools, content, valid):
    write_source(tmp_path, "data.json", content)
    result = code_tools.check_syntax("data.json")
    assert result.ok
    assert result.data["valid"] is valid
    assert bool(result.data["diagnostics"]) is not valid


def test_syntax_and_symbol_inspection_never_execute_or_import_project_code(tmp_path, code_tools):
    marker = tmp_path / "must-not-exist.txt"
    source = (f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
              "import nonexistent_project_dependency_398145\n"
              "raise RuntimeError('must not run')\n"
              "@side_effect()\ndef work():\n    return 1\n")
    write_source(tmp_path, "dangerous.py", source)
    assert code_tools.check_syntax("dangerous.py").data["valid"] is True
    assert code_tools.list_symbols("dangerous.py").ok
    assert code_tools.read_symbol("dangerous.py", "work").ok
    assert not marker.exists()
    assert not (tmp_path / "__pycache__").exists()


@pytest.mark.parametrize("method", ["list_symbols", "check_syntax"])
def test_inspection_rejects_oversize_binary_and_invalid_encoding(tmp_path, code_tools, method):
    operation = getattr(code_tools, method)
    limit = MAX_EDIT_FILE_BYTES if method == "check_syntax" else MAX_READ_BYTES
    (tmp_path / "oversize.py").write_bytes(b"#" * (limit + 1))
    (tmp_path / "binary.py").write_bytes(b"\x00python")
    (tmp_path / "encoding.py").write_bytes(b"value = '\xff'\n")
    assert operation("oversize.py").error_code == "TOO_LARGE"
    assert operation("binary.py").error_code == "BINARY"
    assert operation("encoding.py").error_code == "INVALID_ENCODING"


def test_bom_hash_covers_exact_file_bytes(tmp_path, code_tools):
    raw = b"\xef\xbb\xbfdef work():\n    return 1\n"
    (tmp_path / "bom.py").write_bytes(raw)
    result = code_tools.read_symbol("bom.py", "work")
    assert result.ok
    assert result.data["sha256"] == hashlib.sha256(raw).hexdigest()
    assert result.data["start_line"] == 1
