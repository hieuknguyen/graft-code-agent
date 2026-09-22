"""Atomic edits at multiple source line ranges, without resending removed text."""

from __future__ import annotations

import codecs

from .tool_runtime import MAX_EDIT_FILE_BYTES, MAX_WRITE_BYTES, ToolResult, ToolRuntimeError


MAX_RANGE_EDITS = 200


def propose_line_edits(runtime, path: str, edits: list[dict], expected_sha256: str, description: str = "") -> ToolResult:
    """Replace inclusive lines; end=start-1 inserts before start (including EOF)."""
    try:
        if not isinstance(description, str):
            raise ToolRuntimeError("INVALID_ARGUMENTS", "description phải là chuỗi.")
        if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_RANGE_EDITS:
            raise ToolRuntimeError("INVALID_EDITS", "Cần từ 1 đến 200 vùng sửa trong một lần gọi.")
        full_path, relative = runtime.policy.resolve_read_path(path)
        if full_path.stat().st_size > MAX_EDIT_FILE_BYTES:
            raise ToolRuntimeError("TOO_LARGE", "File vượt giới hạn sửa 8 MB.")
        with full_path.open("rb") as handle:
            raw = handle.read(MAX_EDIT_FILE_BYTES + 1)
        if len(raw) > MAX_EDIT_FILE_BYTES:
            raise ToolRuntimeError("TOO_LARGE", "File vượt giới hạn sửa 8 MB.")
        if b"\x00" in raw:
            raise ToolRuntimeError("BINARY", "Không hỗ trợ sửa file nhị phân.")
        if expected_sha256 != runtime._sha256_bytes(raw):
            raise ToolRuntimeError("STALE_CONTENT", "File đã thay đổi. Đọc lại để lấy số dòng mới.")
        source = raw.decode("utf-8-sig")
        lines = source.splitlines(keepends=True)
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line))
        without_crlf = source.replace("\r\n", "")
        newline = "\r\n" if "\r\n" in source and "\r" not in without_crlf and "\n" not in without_crlf else "\n"
        spans = []
        insertion_points = set()
        for index, edit in enumerate(edits, 1):
            if not isinstance(edit, dict) or set(edit) != {"start_line", "end_line", "new_text"}:
                raise ToolRuntimeError("INVALID_EDITS", f"Vùng {index} phải có start_line, end_line và new_text.")
            start, end, replacement = edit["start_line"], edit["end_line"], edit["new_text"]
            if type(start) is not int or type(end) is not int or not isinstance(replacement, str) or "\x00" in replacement:
                raise ToolRuntimeError("INVALID_EDITS", f"Vùng {index} có số dòng hoặc nội dung không hợp lệ.")
            if not 1 <= start <= len(lines) + 1 or not start - 1 <= end <= len(lines):
                raise ToolRuntimeError("INVALID_RANGE", f"Vùng {index} nằm ngoài file có {len(lines)} dòng.")
            first, last = offsets[start - 1], offsets[end]
            if start == end + 1:
                if first in insertion_points:
                    raise ToolRuntimeError("OVERLAPPING_EDITS", "Gộp các phần chèn tại cùng vị trí thành một vùng.")
                insertion_points.add(first)
            if newline == "\r\n":
                replacement = replacement.replace("\r\n", "\n").replace("\n", "\r\n")
            if replacement and not replacement.endswith(("\r", "\n")):
                # Keep full-line edits separate from retained lines and preserve
                # the original final newline when replacing a terminated range.
                if last < len(source) or (last > first and source[last - 1:last] in {"\n", "\r"}):
                    replacement += newline
            if replacement and first == last == len(source) and source and not source.endswith(("\r", "\n")):
                replacement = newline + replacement
            spans.append((first, last, replacement))
        spans.sort(key=lambda span: (span[0], span[1]))
        cursor = 0
        pieces = []
        for first, last, replacement in spans:
            if first < cursor:
                raise ToolRuntimeError("OVERLAPPING_EDITS", "Các vùng sửa chồng lấn nhau; hãy gộp thành một vùng.")
            pieces.extend([source[cursor:first], replacement])
            cursor = last
        pieces.append(source[cursor:])
        content = "".join(pieces)
        if content == source:
            raise ToolRuntimeError("NO_CHANGE", "Các vùng sửa không làm thay đổi file.")
        if raw.startswith(codecs.BOM_UTF8):
            content = "\ufeff" + content
        if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
            raise ToolRuntimeError("TOO_LARGE", "Nội dung sau khi sửa vượt giới hạn 8 MB.")
        result = runtime.propose_write_file(relative.as_posix(), content, expected_sha256, description)
        if result.ok:
            result.data.update({"edit_count": len(edits), "status": "pending", "original_lines": len(lines),
                                "result_lines": len(content.splitlines())})
        return result
    except ToolRuntimeError as exc:
        return ToolResult(False, error=exc.message, error_code=exc.code)
    except UnicodeError:
        return ToolResult(False, error="File và nội dung sửa phải là UTF-8.", error_code="INVALID_ENCODING")
    except OSError as exc:
        return ToolResult(False, error=str(exc), error_code="EDIT_PROPOSAL_FAILED")
