"""Bounded, read-only code inspection tools for an imported workspace."""

from __future__ import annotations

import ast
import bisect
import fnmatch
import io
import json
import os
import tokenize
import warnings
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from graft.parser import ASTSymbol, parse_python_ast

from .tool_runtime import MAX_EDIT_FILE_BYTES, MAX_READ_BYTES, MAX_READ_CHARS, MAX_SEARCH_FILES, ToolResult, ToolRuntimeError

if TYPE_CHECKING:
    from .tool_runtime import ToolRuntime


MAX_SYMBOLS = 250
PYTHON_SUFFIXES = {".py", ".pyi"}


class CodeTools:
    """Inspect files without importing project modules or executing project code."""

    def __init__(self, runtime: "ToolRuntime"):
        self.runtime = runtime

    def _failure(self, exc: Exception, fallback: str) -> ToolResult:
        code = exc.code if isinstance(exc, ToolRuntimeError) else fallback
        return ToolResult(False, error=self.runtime.redact_text(str(exc))[:2000], error_code=code)

    @staticmethod
    def _glob_matches(path: str, pattern: str) -> bool:
        """A bare pattern matches basenames; ** matches zero or more directories."""
        if os.name == "nt":
            path, pattern = path.casefold(), pattern.casefold()
        if "/" not in pattern:
            return fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], pattern)
        parts, patterns = path.split("/"), pattern.split("/")

        @lru_cache(maxsize=None)
        def match(i: int, j: int) -> bool:
            if j == len(patterns):
                return i == len(parts)
            if patterns[j] == "**":
                return match(i, j + 1) or (i < len(parts) and match(i + 1, j))
            return i < len(parts) and fnmatch.fnmatchcase(parts[i], patterns[j]) and match(i + 1, j + 1)

        return match(0, 0)

    def find_files(self, pattern: str, max_results: int = 100, offset: int = 0) -> ToolResult:
        try:
            if not isinstance(pattern, str) or not pattern.strip() or len(pattern) > 256:
                raise ToolRuntimeError("INVALID_PATTERN", "Mẫu tìm file phải là chuỗi từ 1 đến 256 ký tự.")
            relative = self.runtime.policy._normalise_relative_path(pattern)
            self.runtime.policy._check_segments(relative)
            normalised = relative.as_posix()
            try:
                limit = max(1, min(int(max_results), 200))
                start = int(offset)
            except (TypeError, ValueError, OverflowError):
                raise ToolRuntimeError("INVALID_RANGE", "max_results và offset phải là số nguyên.")
            if start < 0 or start > MAX_SEARCH_FILES:
                raise ToolRuntimeError("INVALID_RANGE", f"offset phải nằm trong khoảng 0 đến {MAX_SEARCH_FILES}.")
            matches: list[dict[str, Any]] = []
            scanned = 0
            scan_truncated = False
            for full_path, rel_path in self.runtime._iter_safe_files():
                if scanned >= MAX_SEARCH_FILES:
                    scan_truncated = True
                    break
                scanned += 1
                if not self._glob_matches(rel_path.as_posix(), normalised):
                    continue
                try:
                    # Validate again: junctions and changes during traversal must
                    # not expose paths outside the imported project.
                    safe_path, safe_relative = self.runtime.policy.resolve_read_path(rel_path.as_posix())
                    matches.append({"path": safe_relative.as_posix(), "bytes": safe_path.stat().st_size})
                except (OSError, ToolRuntimeError):
                    continue
            matches.sort(key=lambda row: (row["path"].casefold(), row["path"]))
            page: list[dict[str, Any]] = []
            output_chars = 0
            for row in matches[start:start + limit]:
                row_chars = len(json.dumps(row, ensure_ascii=False))
                if output_chars + row_chars > MAX_READ_CHARS:
                    break
                page.append(row)
                output_chars += row_chars
            next_offset = start + len(page) if start + len(page) < len(matches) else None
            self.runtime._audit("find_files", pattern=normalised, results=len(page), offset=start)
            return ToolResult(True, {
                "pattern": normalised,
                "files": page,
                "offset": start,
                "returned_count": len(page),
                "total_matches": len(matches),
                "total_matches_is_exact": not scan_truncated,
                "scanned_files": scanned,
                "scan_truncated": scan_truncated,
                "next_offset": next_offset,
                "truncated": next_offset is not None or scan_truncated,
                "note": "Mẫu không có '/' khớp tên file ở mọi thư mục; '**/' gồm cả thư mục gốc. Kết quả phân trang có thể thay đổi khi dự án thay đổi.",
            })
        except (ToolRuntimeError, OSError, RecursionError) as exc:
            return self._failure(exc, "FIND_FAILED")

    def _load_source(self, path: str, max_bytes: int = MAX_READ_BYTES) -> tuple[Path, str, str]:
        full_path, relative = self.runtime.policy.resolve_read_path(path)
        if full_path.stat().st_size > max_bytes:
            raise ToolRuntimeError("TOO_LARGE", f"File vượt giới hạn đọc {max_bytes // 1024} KB.")
        with full_path.open("rb") as handle:
            raw = handle.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ToolRuntimeError("TOO_LARGE", f"File vượt giới hạn đọc {max_bytes // 1024} KB.")
        if self.runtime._is_binary(raw):
            raise ToolRuntimeError("BINARY", "Không hỗ trợ phân tích file nhị phân.")
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ToolRuntimeError("INVALID_ENCODING", "Phân tích code hiện yêu cầu file UTF-8.")
        return relative, content, self.runtime._sha256_bytes(raw)

    @staticmethod
    def _validated_python_tree(relative: Path, content: str) -> ast.Module:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(content, filename=relative.as_posix())
            # AST parsing alone accepts `return`/`break` outside their valid
            # contexts. Compilation checks those without executing the code.
            compile(tree, relative.as_posix(), "exec", dont_inherit=True)
        return tree

    @staticmethod
    def _require_python(relative: Path) -> None:
        if relative.suffix.lower() not in PYTHON_SUFFIXES:
            raise ToolRuntimeError(
                "UNSUPPORTED_LANGUAGE",
                "Công cụ symbol hiện hỗ trợ Python (.py, .pyi). Dùng search_project/read_file cho ngôn ngữ khác.",
            )

    def _python_symbols(self, relative: Path, content: str) -> list[ASTSymbol]:
        self._require_python(relative)
        try:
            tree = self._validated_python_tree(relative, content)
        except (SyntaxError, ValueError) as exc:
            line = getattr(exc, "lineno", None)
            message = getattr(exc, "msg", str(exc))
            raise ToolRuntimeError("SYNTAX_ERROR", f"Python không hợp lệ ở dòng {line or '?'}: {message}") from exc
        parsed = parse_python_ast(content, relative.as_posix())
        existing = {(sym.start_line, sym.name): sym for sym in parsed.symbols}
        symbols: list[ASTSymbol] = []
        decorator_lines: dict[int, list[int]] = {}
        statement_start = True
        for token in tokenize.generate_tokens(io.StringIO(content).readline):
            if token.type == tokenize.NEWLINE:
                statement_start = True
            elif token.type not in (tokenize.NL, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT):
                if statement_start and token.type == tokenize.OP and token.string == "@":
                    decorator_lines.setdefault(token.start[1], []).append(token.start[0])
                statement_start = False

        def visit(node: ast.AST, parent: str = "", parent_is_class: bool = False) -> None:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                is_class = isinstance(node, ast.ClassDef)
                symbol_type = "class" if is_class else ("method" if parent_is_class else "function")
                start = min([node.lineno] + [decorator.lineno for decorator in node.decorator_list])
                if node.decorator_list:
                    starts = decorator_lines.get(node.col_offset, [])
                    index = bisect.bisect_right(starts, start) - 1
                    if index >= 0:
                        start = starts[index]
                end = node.end_lineno or node.lineno
                base = existing.get((node.lineno, node.name), ASTSymbol(node.name, symbol_type, start, end))
                symbols.append(replace(base, symbol_type=symbol_type, start_line=start, end_line=end,
                                       parent=parent or None, source_slice=None))
                parent = f"{parent}.{node.name}" if parent else node.name
                parent_is_class = is_class
            for child in ast.iter_child_nodes(node):
                visit(child, parent, parent_is_class)

        visit(tree)
        return symbols

    @staticmethod
    def _symbol_row(symbol: ASTSymbol) -> dict[str, Any]:
        return {
            "name": symbol.name,
            "type": symbol.symbol_type,
            "parent": symbol.parent or "",
            "qualified_name": f"{symbol.parent}.{symbol.name}" if symbol.parent else symbol.name,
            "start_line": symbol.start_line,
            "end_line": symbol.end_line,
        }

    def list_symbols(self, path: str) -> ToolResult:
        try:
            relative, content, source_hash = self._load_source(path)
            symbols = self._python_symbols(relative, content)
            rows: list[dict[str, Any]] = []
            output_chars = 0
            for symbol in symbols[:MAX_SYMBOLS]:
                row = self._symbol_row(symbol)
                row_chars = len(json.dumps(row, ensure_ascii=False))
                if output_chars + row_chars > MAX_READ_CHARS:
                    break
                rows.append(row)
                output_chars += row_chars
            self.runtime._audit("list_symbols", path=relative.as_posix(), results=len(rows))
            return ToolResult(True, {
                "path": relative.as_posix(), "sha256": source_hash, "language": "Python",
                "symbols": rows, "total_symbols": len(symbols), "total_lines": len(content.splitlines()),
                "truncated": len(rows) < len(symbols),
                "note": "Phạm vi dòng gồm decorator. parent là tên đầy đủ của class/hàm bao ngoài. File hợp lệ có thể không có định nghĩa symbol.",
            })
        except (ToolRuntimeError, OSError, RecursionError, MemoryError) as exc:
            return self._failure(exc, "SYMBOLS_FAILED")

    def read_symbol(self, path: str, symbol: str, parent: str = "") -> ToolResult:
        try:
            if not isinstance(symbol, str) or not symbol.strip() or len(symbol) > 512:
                raise ToolRuntimeError("INVALID_SYMBOL", "Tên symbol phải là chuỗi không rỗng, tối đa 512 ký tự.")
            if not isinstance(parent, str) or len(parent) > 512:
                raise ToolRuntimeError("INVALID_SYMBOL", "parent phải là chuỗi tối đa 512 ký tự.")
            relative, content, source_hash = self._load_source(path)
            symbols = self._python_symbols(relative, content)
            name, parent = symbol.strip(), parent.strip()
            matches = [item for item in symbols
                       if name in (item.name, self._symbol_row(item)["qualified_name"])
                       and (not parent or item.parent == parent)]
            if not matches:
                raise ToolRuntimeError("SYMBOL_NOT_FOUND", "Không tìm thấy symbol. Dùng list_symbols để lấy tên và parent.")
            if len(matches) > 1:
                candidates = ", ".join(f"{self._symbol_row(item)['qualified_name']} (dòng {item.start_line})"
                                       for item in matches[:8])
                raise ToolRuntimeError("AMBIGUOUS_SYMBOL", f"Có {len(matches)} symbol trùng tên: {candidates}. Chỉ định parent hoặc dùng read_file theo dòng.")
            selected = matches[0]
            result = self.runtime.read_file(relative.as_posix(), selected.start_line, selected.end_line)
            if not result.ok:
                return result
            if result.data["sha256"] != source_hash:
                self.runtime.forget_read(relative.as_posix())
                raise ToolRuntimeError("STALE_CONTENT", "File thay đổi trong lúc đọc symbol; hãy gọi lại để lấy phiên bản mới.")
            result.data.update({
                "symbol": self._symbol_row(selected),
                "truncated": result.data["end_line"] < selected.end_line
                             or len(result.data["content"]) >= MAX_READ_CHARS,
            })
            self.runtime._audit("read_symbol", path=relative.as_posix(), symbol=name, parent=parent)
            return result
        except (ToolRuntimeError, OSError, RecursionError, MemoryError) as exc:
            return self._failure(exc, "SYMBOL_READ_FAILED")

    def check_syntax(self, path: str) -> ToolResult:
        try:
            relative, content, source_hash = self._load_source(path, MAX_EDIT_FILE_BYTES)
            syntax = self.runtime.inspect_syntax(relative.as_posix(), content)
            valid = None if syntax["status"] == "unavailable" else syntax["status"] == "valid"
            self.runtime._audit("check_syntax", path=relative.as_posix(), valid=valid)
            return ToolResult(True, {
                "path": relative.as_posix(), "sha256": source_hash,
                **syntax, "valid": valid, "syntax": syntax,
                "note": "Chỉ kiểm tra cú pháp; không thực thi code, import module, kiểm tra kiểu hay chạy test.",
            })
        except (ToolRuntimeError, OSError, RecursionError, MemoryError) as exc:
            return self._failure(exc, "SYNTAX_CHECK_FAILED")
