"""Syntax results distinguish actual source errors from unavailable checkers."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from core import verifier
from core.verifier import validate_syntax, verify_code


@pytest.mark.parametrize("source", [
    "return 1", "break", "continue", "await run()",
    "nonlocal value", "def broken(:\n    pass\n", "value = " + chr(0),
])
def test_python_reports_compile_time_context_and_parse_errors(source):
    result = validate_syntax("src/module.py", source)
    assert result["status"] == "invalid"
    assert result["checked"] is True
    assert result["language"] == "python"
    assert result["diagnostics"][0]["line"] >= 1
    assert result["diagnostics"][0]["column"] >= 1


def test_python_compiles_without_execution_imports_or_files(tmp_path):
    marker = tmp_path / "must-not-exist"
    source = (
        "import project_module_that_does_not_exist\n"
        f"open({str(marker)!r}, 'w').write('executed')\n"
        "raise RuntimeError('must not run')\n"
    )
    with patch("builtins.open", side_effect=AssertionError("Must not write a file")):
        result = validate_syntax("module.py", source)
    assert result["status"] == "valid"
    assert not marker.exists()


def test_python_error_location_preserves_full_file_line_number():
    result = validate_syntax("module.py", "# header\n" * 2500 + "def broken(:\n    pass\n")
    diagnostic = result["diagnostics"][0]
    assert diagnostic["line"] == 2501
    assert diagnostic["excerpt"] == "def broken(:"


def test_python_supports_bom_and_windows_newlines():
    assert validate_syntax("Module.PYW", "\ufeffvalue = 1\r\n")["status"] == "valid"


@pytest.mark.parametrize("source", [
    '{"n": NaN}', '{"n": Infinity}', '{"n": -Infinity}', '{"n": 1,}', '{"n":}',
])
def test_json_rejects_nonstandard_numbers_and_malformed_structure(source):
    result = validate_syntax("data.json", source)
    assert result["status"] == "invalid"
    assert result["engine"] == "json"
    assert result["diagnostics"]


def test_json_constant_location_skips_tokens_inside_strings():
    source = '{"text":"NaN and \\"NaN\\"",\n "value": NaN}'
    diagnostic = validate_syntax("data.json", source)["diagnostics"][0]
    assert diagnostic["line"] == 2
    assert diagnostic["column"] == 11
    assert "NaN is not a valid JSON number" in diagnostic["message"]


def test_json_validates_without_tree_sitter():
    with patch.object(verifier, "_get_parser", side_effect=AssertionError("Not required")):
        result = validate_syntax("data.json", '{"items":[1, true, null], "text":"NaN"}')
    assert result["status"] == "valid"


@pytest.mark.parametrize("path", [
    "settings.jsonc", "tsconfig.json", "tsconfig.app.json", "jsconfig.json",
    "jsconfig.dev.json", "project/.vscode/settings.json",
    "C:\\project\\.vscode\\launch.json", "TSCONFIG.BUILD.JSON",
])
def test_project_jsonc_files_allow_comments_and_trailing_commas(path):
    source = '{\n  // project options\n  "compilerOptions": {\n    "strict": true, /* required */\n  },\n}\n'
    with patch.object(verifier, "_get_parser", side_effect=AssertionError("Not required")):
        result = validate_syntax(path, source)
    assert result["status"] == "valid", result
    assert result["language"] == "jsonc"
    assert result["engine"] == "jsonc"


@pytest.mark.parametrize("source", [
    '{"url": "https://example.test/a//b", "pattern": "/* literal */",}',
    '{"text": "escaped \\\"// quote", "literal": ",}", "array": [1,2,],}',
    '{"text": "comma ,] and /* comments */ inside a string",}',
    '{/* comment with a fake \\\"string */ "value": 1,// trailing comment\n}',
    '[true, false, null, /* comment */]',
])
def test_jsonc_preprocessing_preserves_strings_and_nested_trailing_commas(source):
    result = validate_syntax("settings.jsonc", source)
    assert result["status"] == "valid", result


@pytest.mark.parametrize("source", [
    "{,}", "[ , ]", '{"key":,}', "[1,,]", '{"a":1,,}',
    '{"a": 1 "b": 2}', '{"n": NaN}', '{"n": Infinity}',
    '{"n": -Infinity}', '{"value": "unterminated // text}',
    '{"value": "literal\nnewline"}', '{"value": 1} /* unclosed',
    '{"value": 1} /*/',
    '{"value": 1} garbage', '{"a": 1,] ',
])
def test_jsonc_does_not_hide_structural_errors_or_invalid_numbers(source):
    result = validate_syntax("settings.jsonc", source)
    assert result["status"] == "invalid", result
    assert result["language"] == "jsonc"
    assert result["diagnostics"]


def test_jsonc_errors_use_original_lines_and_excerpt_after_multiline_comments():
    source = '{\r\n /* a comment\r\n    spanning two lines */\r\n "broken": ,\r\n}\r\n'
    result = validate_syntax("tsconfig.json", source)
    assert result["status"] == "invalid"
    diagnostic = result["diagnostics"][0]
    assert diagnostic["line"] == 4
    assert diagnostic["column"] == 12
    assert diagnostic["excerpt"] == ' "broken": ,'


def test_unterminated_jsonc_comment_reports_the_opening_location():
    source = '{\n  "value": 1,\n  /* unterminated\n}'
    result = validate_syntax("settings.jsonc", source)
    diagnostic = result["diagnostics"][0]
    assert result["status"] == "invalid"
    assert diagnostic["line"] == 3
    assert diagnostic["column"] == 3
    assert "Unterminated block comment" in diagnostic["message"]


@pytest.mark.parametrize("path", ["package.json", "settings.json", "tsconfig-extra.json", "project/vscode/settings.json"])
def test_ordinary_json_paths_keep_strict_comment_and_trailing_comma_rules(path):
    assert verifier._language_for_path(path) == "json"
    assert validate_syntax(path, '{"value": 1,}')["status"] == "invalid"
    assert validate_syntax(path, '{/* comment */ "value": 1}')["status"] == "invalid"


@pytest.mark.parametrize("path,source", [
    ("data.json", '{"value": 1}\r\n'),
    ("settings.jsonc", '{// comment\r\n "value": 1,\r\n}\r\n'),
    ("tsconfig.json", '{"compilerOptions": {"strict": true,},}\r\n'),
])
def test_json_and_jsonc_accept_retained_utf8_bom(path, source):
    assert validate_syntax(path, "\ufeff" + source)["status"] == "valid"


@pytest.mark.parametrize("path", ["data.json", "settings.jsonc"])
def test_json_bom_errors_use_visible_character_columns(path):
    result = validate_syntax(path, '\ufeff{"value": }')
    assert result["status"] == "invalid"
    diagnostic = result["diagnostics"][0]
    assert diagnostic["line"] == 1
    assert diagnostic["column"] == 11
    assert diagnostic["excerpt"] == '{"value": }'


@pytest.mark.parametrize("path", ["data.json", "settings.jsonc"])
def test_large_json_numbers_are_checked_without_integer_conversion_limits(path):
    source = '{"integer": ' + "9" * 10000 + ', "float": 1e99999999}'
    result = validate_syntax(path, source)
    assert result["status"] == "valid", result


@pytest.mark.parametrize("path,language", [
    ("src/Module.TSX", "tsx"), ("C:\\project\\app.ts", "typescript"),
    ("Dockerfile", "dockerfile"), ("Dockerfile.dev", "dockerfile"),
    ("Containerfile", "dockerfile"), ("src/Makefile", "make"),
    ("CMakeLists.txt", "cmake"), ("go.mod", "gomod"), ("Gemfile", "ruby"),
    ("src/main.js", "javascript"), ("src/main.jsx", "javascript"),
    ("src/main.php", "php"), ("src/main.cs", "csharp"),
    ("src/main.cpp", "cpp"), ("src/main.c", "c"),
    ("src/main.h", "cpp"), ("src/main.rs", "rust"),
    ("src/app.vue", "vue"), ("src/style.scss", "scss"),
])
def test_language_detection_is_based_on_project_file(path, language):
    assert verifier._language_for_path(path) == language


@pytest.mark.parametrize("path", ["notes.txt", "view.blade.php", "unknown.custom"])
def test_unsupported_formats_explicitly_report_unavailable(path):
    result = validate_syntax(path, "anything")
    assert result["status"] == "unavailable"
    assert result["checked"] is False
    assert result["reason"] == "unsupported_language"
    assert not result["diagnostics"]
    compatible, message = verify_code(path, "anything")
    assert compatible is True
    assert "unavailable" in message
    assert "passed" not in message.lower()


def test_missing_language_pack_reports_unavailable_without_importing_it():
    with patch.object(verifier.metadata, "version", side_effect=verifier.metadata.PackageNotFoundError), \
         patch.object(verifier.importlib, "import_module") as loader:
        result = validate_syntax("main.js", "const x = 1;")
    assert result["status"] == "unavailable"
    assert result["reason"] == "parser_unavailable"
    loader.assert_not_called()


def test_future_language_pack_is_not_imported_or_allowed_to_download():
    with patch.object(verifier.metadata, "version", return_value="1.17.0"), \
         patch.object(verifier.importlib, "import_module") as loader:
        result = validate_syntax("main.js", "const x = 1;")
    assert result["status"] == "unavailable"
    loader.assert_not_called()


def test_parse_timeout_is_unavailable_not_valid():
    with patch.object(verifier, "_get_parser", return_value=Mock(parse=Mock(return_value=None))):
        result = validate_syntax("main.js", "const x = 1;")
    assert result["status"] == "unavailable"
    assert result["reason"] == "parser_limit"


def test_parse_failure_is_unavailable_not_a_source_error():
    with patch.object(verifier, "_get_parser", return_value=Mock(parse=Mock(side_effect=RuntimeError))):
        result = validate_syntax("main.js", "const x = 1;")
    assert result["status"] == "unavailable"
    assert result["reason"] == "parser_error"


def fake_node(*, row=0, column=0, start_byte=0, error=False, missing=False, children=()):
    return SimpleNamespace(
        is_missing=missing, is_error=error,
        has_error=error or missing or any(node.has_error for node in children),
        start_point=(row, column), end_point=(row, column + 1),
        start_byte=start_byte, type=")" if missing else "ERROR",
        children=children,
    )


def test_missing_node_diagnostic_and_unicode_column_use_character_offsets():
    source = "é = ("
    node = fake_node(column=6, start_byte=6, missing=True)
    root = fake_node(children=[node])
    with patch.object(verifier, "_get_parser", return_value=Mock(
            parse=Mock(return_value=SimpleNamespace(root_node=root)))):
        result = validate_syntax("main.js", source)
    assert result["status"] == "invalid"
    assert result["diagnostics"][0]["column"] == 6
    assert result["diagnostics"][0]["message"] == "Missing ')'"


def test_diagnostics_are_capped_and_report_truncation():
    source = "\n".join("x = ;" for _ in range(100))
    root = fake_node(children=[
        fake_node(row=row, column=4, start_byte=row * 6 + 4, error=True) for row in range(100)
    ])
    with patch.object(verifier, "_get_parser", return_value=Mock(
            parse=Mock(return_value=SimpleNamespace(root_node=root)))):
        result = validate_syntax("main.js", source)
    assert len(result["diagnostics"]) == verifier.MAX_SYNTAX_DIAGNOSTICS
    assert result["diagnostics_truncated"] is True
    assert result["diagnostics"][-1]["line"] == verifier.MAX_SYNTAX_DIAGNOSTICS


def test_syntax_result_limits_large_files_and_large_excerpts(monkeypatch):
    monkeypatch.setattr(verifier, "MAX_SYNTAX_BYTES", 20)
    assert validate_syntax("file.py", "#" * 21)["reason"] == "size_limit"
    assert validate_syntax("file.py", "é" * 11)["reason"] == "size_limit"
    monkeypatch.setattr(verifier, "MAX_SYNTAX_BYTES", 10000)
    result = validate_syntax("file.py", "x = " + " " * 1000 + ")")
    assert len(result["diagnostics"][0]["excerpt"]) <= verifier.MAX_DIAGNOSTIC_EXCERPT + 1


def test_invalid_input_does_not_crash_the_app():
    assert validate_syntax("file.py", None)["reason"] == "invalid_input"
    assert validate_syntax("file.py", "\ud800")["status"] == "invalid"


@pytest.mark.parametrize("path,valid,invalid", [
    ("config.toml", 'name = "app"\n', 'name = [\n'),
    ("config.yaml", 'name: app\nlist: [1, 2]\n', 'list: [1, 2\n'),
])
def test_configuration_syntax(path, valid, invalid):
    assert validate_syntax(path, valid)["status"] == "valid"
    assert validate_syntax(path, invalid)["status"] == "invalid"


def test_yaml_does_not_execute_tagged_objects():
    source = "!!python/object/apply:os.system ['must-not-execute']"
    with patch("os.system", side_effect=AssertionError("Must not execute")):
        result = validate_syntax("data.yaml", source)
    assert result["status"] == "valid"


@pytest.mark.parametrize("path,valid,invalid", [
    ("main.js", "const x = 1;", "const x = ;"),
    ("view.jsx", "const App = () => <div>Hello</div>;", "const App = () => <div>;"),
    ("main.ts", "const x: number = 1;", "const x: = ;"),
    ("view.tsx", "const App = () => <div>Hello</div>;", "const App = () => <div>;"),
    ("main.php", "<?php function f() { return 1; }", "<?php function f( {"),
    ("main.go", "package main\nfunc main() {}\n", "package main\nfunc main( {\n"),
    ("main.rs", "fn main() {}", "fn main( {"),
    ("Main.java", "class Main { int x = 1; }", "class Main { int x = ; }"),
    ("main.c", "int main(void) { return 0; }", "int main( {"),
    ("main.cpp", "int main() { return 0; }", "int main( {"),
    ("Main.cs", "class Main { int x = 1; }", "class Main { int x = ; }"),
    ("style.css", "body { color: red; }", "body { color: ;"),
    ("index.html", "<html><body>Hello</body></html>", "<div foo=\""),
    ("query.sql", "SELECT id FROM users;", "SELECT * FROM ;"),
    ("Dockerfile", "FROM python:3.14\nRUN echo hello\n", "FROM\n"),
    ("Makefile", "all:\n\techo hello\n", "all: $(missing\n"),
])
def test_real_bundled_parsers_find_language_syntax_errors(path, valid, invalid):
    try:
        version = verifier.metadata.version("tree-sitter-language-pack")
    except verifier.metadata.PackageNotFoundError:
        pytest.skip("Install requirements to run bundled parser integration tests")
    if version != "0.13.0":
        pytest.skip("Requires the pinned offline language pack")
    good = validate_syntax(path, valid)
    broken = validate_syntax(path, invalid)
    assert good["status"] == "valid", good
    assert broken["status"] == "invalid", broken
    assert broken["diagnostics"][0]["line"] >= 1
    assert broken["diagnostics"][0]["column"] >= 1


def test_verify_code_keeps_legacy_boolean_contract():
    assert verify_code("file.py", "x = 1")[0] is True
    ok, message = verify_code("file.py", "def broken(:")
    assert ok is False
    assert "Line 1" in message
