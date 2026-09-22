"""Bounded, offline syntax diagnostics without executing project code or tools."""

from __future__ import annotations

import importlib
import json
import re
import warnings
from importlib import metadata
from pathlib import PurePosixPath
from typing import Any, Tuple


MAX_SYNTAX_BYTES = 8 * 1024 * 1024
MAX_SYNTAX_DIAGNOSTICS = 20
MAX_DIAGNOSTIC_EXCERPT = 240
TREE_SITTER_TIMEOUT_MICROS = 2_000_000

# Grammar IDs in the bundled language pack. Unknown extensions stay unchecked.
_EXTENSIONS = {
    ".py": "python", ".pyw": "python", ".pyi": "python",
    ".json": "json", ".ipynb": "json", ".jsonc": "jsonc",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".jsx": "javascript", ".ts": "typescript", ".mts": "typescript",
    ".cts": "typescript", ".tsx": "tsx",
    ".php": "php", ".phtml": "php", ".go": "go", ".rs": "rust",
    ".java": "java", ".c": "c", ".h": "cpp", ".cc": "cpp",
    ".cpp": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp",
    ".hxx": "cpp", ".cs": "csharp", ".csx": "csharp",
    ".html": "html", ".htm": "html", ".css": "css", ".scss": "scss",
    ".vue": "vue", ".svelte": "svelte", ".astro": "astro",
    ".yaml": "yaml", ".yml": "yaml", ".toml": "toml", ".sql": "sql",
    ".sh": "bash", ".bash": "bash", ".fish": "fish",
    ".ps1": "powershell", ".psm1": "powershell", ".psd1": "powershell",
    ".rb": "ruby", ".rake": "ruby", ".gemspec": "ruby", ".lua": "lua",
    ".luau": "luau", ".kt": "kotlin", ".kts": "kotlin", ".swift": "swift",
    ".dart": "dart", ".scala": "scala", ".sc": "scala", ".r": "r",
    ".ex": "elixir", ".exs": "elixir", ".erl": "erlang", ".hrl": "erlang",
    ".hs": "haskell", ".ml": "ocaml",
    ".mli": "ocaml_interface", ".fs": "fsharp", ".fsi": "fsharp_signature",
    ".fsx": "fsharp", ".clj": "clojure", ".cljs": "clojure",
    ".cljc": "clojure", ".edn": "clojure", ".pl": "perl", ".pm": "perl",
    ".jl": "julia", ".zig": "zig", ".nim": "nim", ".nix": "nix",
    ".d": "d", ".v": "verilog", ".sv": "verilog", ".svh": "verilog",
    ".vhd": "vhdl", ".vhdl": "vhdl", ".f": "fortran", ".f90": "fortran",
    ".f95": "fortran", ".f03": "fortran", ".f08": "fortran",
    ".groovy": "groovy", ".gradle": "groovy", ".proto": "proto",
    ".graphql": "graphql", ".gql": "graphql", ".prisma": "prisma",
    ".tf": "terraform", ".tfvars": "terraform", ".hcl": "hcl",
    ".sol": "solidity", ".gd": "gdscript", ".glsl": "glsl",
    ".vert": "glsl", ".frag": "glsl", ".wgsl": "wgsl", ".hlsl": "hlsl",
    ".xml": "xml", ".xsd": "xml", ".xsl": "xml", ".svg": "xml",
    ".cmake": "cmake", ".mk": "make", ".dockerfile": "dockerfile",
    ".bzl": "starlark", ".bazel": "starlark", ".elm": "elm",
    ".gleam": "gleam", ".tcl": "tcl", ".rkt": "racket",
    ".scm": "scheme", ".lisp": "commonlisp", ".el": "elisp",
}
_FILENAMES = {
    "dockerfile": "dockerfile", "containerfile": "dockerfile",
    "makefile": "make", "gnumakefile": "make", "cmakelists.txt": "cmake",
    "gemfile": "ruby", "rakefile": "ruby", "vagrantfile": "ruby",
    "go.mod": "gomod", "go.sum": "gosum", "build": "starlark",
    "workspace": "starlark", "meson.build": "meson", "meson_options.txt": "meson",
}


def _language_for_path(file_path: str) -> str:
    path = PurePosixPath(str(file_path).replace("\\", "/").lower())
    name = path.name
    if (name == "tsconfig.json" or name == "jsconfig.json"
            or name.startswith(("tsconfig.", "jsconfig.")) and name.endswith(".json")
            or path.parent.name == ".vscode" and name.endswith(".json")):
        return "jsonc"
    # The PHP grammar cannot reliably validate mixed Blade directives.
    if name.endswith(".blade.php"):
        return "blade"
    if name in _FILENAMES:
        return _FILENAMES[name]
    if name.startswith(("dockerfile.", "containerfile.")):
        return "dockerfile"
    return _EXTENSIONS.get(PurePosixPath(name).suffix, "unknown")


def _result(status: str, language: str, diagnostics: list[dict] | None = None,
            *, engine: str | None = None, reason: str | None = None,
            summary: str | None = None, truncated: bool = False) -> dict[str, Any]:
    result = {
        "status": status,
        "language": language,
        "diagnostics": diagnostics or [],
        "checked": status != "unavailable",
        "engine": engine,
        "summary": summary or (
            f"No syntax errors found by {engine} ({language})."
            if status == "valid" else f"Syntax errors found ({language})."
        ),
        "diagnostics_truncated": truncated,
    }
    if reason:
        result["reason"] = reason
    return result


def _unavailable(language: str, reason: str, message: str, engine: str | None = None) -> dict:
    return _result("unavailable", language, engine=engine, reason=reason,
                   summary=f"Syntax check unavailable ({language}): {message}")


def _diagnostic(code: str, message: str, line: int | None = 1,
                column: int | None = 1, end_line: int | None = None) -> dict:
    line, column = max(1, line or 1), max(1, column or 1)
    # Only retain the relevant line; avoid repeatedly splitting a multi-MB file.
    start = 0
    for _ in range(line - 1):
        newline = code.find("\n", start)
        if newline < 0:
            start = len(code)
            break
        start = newline + 1
    end = code.find("\n", start)
    end = len(code) if end < 0 else end
    excerpt = code[start:min(end, start + MAX_DIAGNOSTIC_EXCERPT)].rstrip("\r")
    if end - start > MAX_DIAGNOSTIC_EXCERPT:
        excerpt += "…"
    result = {"message": message[:1000], "line": line, "column": column, "excerpt": excerpt}
    if end_line is not None:
        result["end_line"] = max(line, end_line)
    return result


class _JSONConstantError(ValueError):
    pass


def _reject_json_constant(value: str) -> None:
    raise _JSONConstantError(value)


def _validate_json(code: str) -> dict:
    # A UTF-8 file may retain its encoding marker in an edit proposal. The
    # marker is not part of the first displayed source column.
    code = code.removeprefix("\ufeff")
    try:
        # Validate number tokens without materializing arbitrary-size integers;
        # Python's integer conversion limit is not a JSON syntax restriction.
        json.loads(code, parse_constant=_reject_json_constant,
                   parse_int=lambda token: None, parse_float=lambda token: None)
    except json.JSONDecodeError as exc:
        return _result("invalid", "json", [_diagnostic(code, exc.msg, exc.lineno, exc.colno)],
                       engine="json")
    except _JSONConstantError as exc:
        token = str(exc)
        # Skip quoted strings when locating the first non-standard number token.
        position = next((match.start() for match in re.finditer(
            r'"(?:\\.|[^"\\])*"|(?P<constant>-?Infinity|NaN)', code
        ) if match.group("constant") == token), 0)
        line = code.count("\n", 0, position) + 1
        column = position - code.rfind("\n", 0, position)
        return _result("invalid", "json", [_diagnostic(
            code, f"{token} is not a valid JSON number", line, column
        )], engine="json")
    return _result("valid", "json", engine="json")


def _validate_jsonc(code: str) -> dict:
    """Allow comments and trailing commas while preserving diagnostic offsets."""
    code = code.removeprefix("\ufeff")

    def strip_comment(match):
        token = match.group()
        if token.startswith('"'):
            return token
        if token.startswith("/*") and (len(token) < 4 or not token.endswith("*/")):
            raise json.JSONDecodeError("Unterminated block comment", code, match.start())
        return "".join(character if character in "\r\n" else " " for character in token)

    try:
        clean = re.sub(r'"(?:\\.|[^"\\])*"|//[^\r\n]*|/\*[\s\S]*?(?:\*/|\Z)', strip_comment, code)
    except json.JSONDecodeError as exc:
        return _result("invalid", "jsonc", [_diagnostic(code, exc.msg, exc.lineno, exc.colno)],
                       engine="jsonc")

    def strip_trailing_comma(match):
        if match.group() != ",":
            return match.group()
        previous = match.start() - 1
        while previous >= 0 and clean[previous].isspace():
            previous -= 1
        # An orphan comma is invalid even in JSONC: {,}, [ ,], {"key":,}.
        return " " if previous >= 0 and clean[previous] not in "{[,:" else ","

    clean = re.sub(r'"(?:\\.|[^"\\])*"|,(?=\s*[}\]])', strip_trailing_comma, clean)
    result = _validate_json(clean)
    return _result(result["status"], "jsonc", [
        _diagnostic(code, item["message"], item["line"], item["column"])
        for item in result["diagnostics"]
    ], engine="jsonc")


def _get_parser(language: str):
    # v0.13 bundles grammars. Later versions download grammars at first use;
    # this verifier must never trigger a network request while editing a file.
    try:
        version = metadata.version("tree-sitter-language-pack")
    except metadata.PackageNotFoundError:
        raise ImportError("Install project requirements to enable this language's parser.") from None
    if version != "0.13.0":
        raise ImportError("Install tree-sitter-language-pack==0.13.0 from project requirements.")
    package = importlib.import_module("tree_sitter_language_pack")
    parser = package.get_parser(language)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        parser.timeout_micros = TREE_SITTER_TIMEOUT_MICROS
    return parser


def _tree_sitter_diagnostics(root, code: str, source: bytes) -> tuple[list[dict], bool]:
    diagnostics = []
    pending = [root]
    seen = set()
    while pending and len(diagnostics) < MAX_SYNTAX_DIAGNOSTICS:
        node = pending.pop()
        missing = node.is_missing
        if node.is_error or missing:
            row, byte_column = node.start_point
            # Tree-sitter counts UTF-8 bytes; public columns count characters.
            line_start = source.rfind(b"\n", 0, node.start_byte) + 1
            column = len(source[line_start:line_start + byte_column].decode("utf-8", errors="replace")) + 1
            key = (row, column, node.type)
            if key not in seen:
                seen.add(key)
                message = f"Missing {node.type!r}" if missing else "Unexpected or incomplete syntax"
                diagnostics.append(_diagnostic(code, message, row + 1, column, node.end_point[0] + 1))
            # Nested ERROR nodes repeat the same broken expression.
            continue
        pending.extend(reversed([
            child for child in node.children if child.has_error or child.is_missing
        ]))
    if not diagnostics:
        diagnostics.append(_diagnostic(code, "The parser found an incomplete syntax tree."))
    return diagnostics, bool(pending)


def _validate_tree_sitter(language: str, code: str, source: bytes) -> dict:
    try:
        parser = _get_parser(language)
    except Exception as exc:
        return _unavailable(language, "parser_unavailable", str(exc), "tree-sitter")
    try:
        tree = parser.parse(source)
        if tree is None:
            return _unavailable(language, "parser_limit", "Parser exceeded its time budget.", "tree-sitter")
        if not tree.root_node.has_error:
            return _result("valid", language, engine="tree-sitter")
        diagnostics, truncated = _tree_sitter_diagnostics(tree.root_node, code, source)
        return _result("invalid", language, diagnostics, engine="tree-sitter", truncated=truncated)
    except Exception as exc:
        # Parser failures stay distinguishable from source syntax errors.
        return _unavailable(language, "parser_error", f"Parser failed: {type(exc).__name__}.", "tree-sitter")


def validate_syntax(file_path: str, code: str) -> dict[str, Any]:
    """Inspect complete file text; never execute it, import it, or write temp files.

    Valid means this parser found no syntax errors, not that project compilation,
    types, imports, embedded languages, or runtime behavior passed. Unavailable
    is explicit for unknown formats, missing parsers, and resource limits.
    Locations use one-based lines and character columns.
    """
    language = _language_for_path(file_path)
    if not isinstance(code, str):
        return _unavailable(language, "invalid_input", "Source must be text.")
    try:
        source = code.encode("utf-8")
    except UnicodeEncodeError:
        return _result("invalid", language, [_diagnostic(code, "Source contains an invalid Unicode character.")],
                       engine="unicode")
    if len(source) > MAX_SYNTAX_BYTES:
        return _unavailable(language, "size_limit", f"File exceeds {MAX_SYNTAX_BYTES} bytes.")
    try:
        if language == "python":
            try:
                compile(code.removeprefix("\ufeff"), str(file_path), "exec", dont_inherit=True)
            except (SyntaxError, ValueError) as exc:
                return _result("invalid", language, [_diagnostic(
                    code, getattr(exc, "msg", str(exc)), getattr(exc, "lineno", 1),
                    getattr(exc, "offset", 1), getattr(exc, "end_lineno", None),
                )], engine="python-compile")
            return _result("valid", language, engine="python-compile")
        if language == "json":
            return _validate_json(code)
        if language == "jsonc":
            return _validate_jsonc(code)
        if language == "toml":
            try:
                import tomllib
            except ImportError:
                return _validate_tree_sitter(language, code, source)
            try:
                tomllib.loads(code)
            except tomllib.TOMLDecodeError as exc:
                return _result("invalid", language, [_diagnostic(
                    code, str(exc), getattr(exc, "lineno", 1), getattr(exc, "colno", 1)
                )], engine="tomllib")
            return _result("valid", language, engine="tomllib")
        if language == "yaml":
            try:
                import yaml
            except ImportError:
                return _validate_tree_sitter(language, code, source)
            try:
                # Parsing events avoids construction, tag handlers, and alias
                # expansion. Project-specific tags remain allowed.
                for _event in yaml.parse(code, Loader=yaml.SafeLoader):
                    pass
            except yaml.YAMLError as exc:
                mark = getattr(exc, "problem_mark", None)
                return _result("invalid", language, [_diagnostic(
                    code, getattr(exc, "problem", None) or str(exc),
                    mark.line + 1 if mark else 1, mark.column + 1 if mark else 1,
                )], engine="pyyaml")
            return _result("valid", language, engine="pyyaml")
        if language in {"unknown", "blade"}:
            return _unavailable(language, "unsupported_language", "No reliable parser configured for this format.")
        return _validate_tree_sitter(language, code, source)
    except (RecursionError, MemoryError, OverflowError):
        return _unavailable(language, "parser_limit", "Source exceeds parser resource limits.")


def verify_code(file_path: str, code: str) -> Tuple[bool, str]:
    """Compatibility wrapper: a skipped check is never described as passed."""
    result = validate_syntax(file_path, code)
    if result["status"] == "unavailable":
        return True, f"Bỏ qua kiểm tra: {result['summary']}"
    if result["status"] == "valid":
        return True, result["summary"]
    details = "\n".join(
        f"Line {item['line']}, column {item['column']}: {item['message']}\n{item['excerpt']}"
        for item in result["diagnostics"]
    )
    return False, f"Lỗi cú pháp ({result['language']}):\n{details}"
