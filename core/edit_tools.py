"""Precise, snapshot-based text edits using the existing approval workflow."""

from __future__ import annotations

import codecs
import re
from typing import TYPE_CHECKING

from core.tool_runtime import MAX_EDIT_FILE_BYTES, MAX_WRITE_BYTES, ToolResult, ToolRuntimeError

if TYPE_CHECKING:
    from core.tool_runtime import ToolRuntime


MAX_EDITS = 100


def propose_edit_file(
    runtime: ToolRuntime,
    path: str,
    edits: list[dict],
    expected_sha256: str,
    description: str = "",
) -> ToolResult:
    """Propose exact replacements anchored to one unchanged UTF-8 snapshot.

    Every old_text must occur exactly once, including overlapping occurrences.
    Edits are independent of input order and cannot target text produced by an
    earlier edit. For consistently CRLF files, LF/CRLF in both edit strings is
    normalized to CRLF; mixed-newline files require exact matching. Only the
    existing proposal mechanism can apply the result.
    """
    try:
        if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
            raise ToolRuntimeError("INVALID_HASH", "Cần SHA-256 hợp lệ từ read_file trước khi đề xuất sửa.")
        if not isinstance(description, str):
            raise ToolRuntimeError("INVALID_ARGUMENTS", "Mô tả thay đổi phải là chuỗi.")
        if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_EDITS:
            raise ToolRuntimeError("INVALID_EDITS", f"Cần từ 1 đến {MAX_EDITS} thay đổi trong danh sách edits.")

        edit_bytes = 0
        for edit in edits:
            if not isinstance(edit, dict) or set(edit) != {"old_text", "new_text"}:
                raise ToolRuntimeError("INVALID_EDITS", "Mỗi thay đổi chỉ gồm old_text và new_text.")
            old_text, new_text = edit["old_text"], edit["new_text"]
            if not isinstance(old_text, str) or not old_text or not isinstance(new_text, str):
                raise ToolRuntimeError("INVALID_EDITS", "old_text phải là chuỗi không rỗng; new_text phải là chuỗi.")
            if old_text == new_text:
                raise ToolRuntimeError("NO_CHANGE", "old_text và new_text giống nhau; không có thay đổi để đề xuất.")
            if "\x00" in old_text or "\x00" in new_text:
                raise ToolRuntimeError("INVALID_EDITS", "Thay đổi văn bản không được chứa ký tự NUL.")
            edit_bytes += len(old_text.encode("utf-8")) + len(new_text.encode("utf-8"))
            if edit_bytes > MAX_WRITE_BYTES:
                raise ToolRuntimeError("TOO_LARGE", "Tổng nội dung thay đổi vượt giới hạn cho phép.")

        full_path, relative = runtime.policy.resolve_read_path(path)
        # Also validate the resolved target: an in-project link must never turn
        # an ordinary-looking requested path into a secret or ignored file.
        resolved_relative = full_path.relative_to(runtime.root_dir)
        runtime.policy._check_segments(resolved_relative)
        if runtime.policy.is_sensitive(resolved_relative):
            raise ToolRuntimeError("SENSITIVE_FILE", "Agent không được đọc hoặc sửa file chứa bí mật.")
        if full_path.stat().st_size > MAX_EDIT_FILE_BYTES:
            raise ToolRuntimeError("TOO_LARGE", "File vượt giới hạn sửa 8 MB.")
        with full_path.open("rb") as handle:
            raw = handle.read(MAX_EDIT_FILE_BYTES + 1)
        if len(raw) > MAX_EDIT_FILE_BYTES:
            raise ToolRuntimeError("TOO_LARGE", "File vượt giới hạn sửa 8 MB.")
        if b"\x00" in raw:
            raise ToolRuntimeError("BINARY", "Không thể sửa file nhị phân qua công cụ văn bản.")
        source_hash = runtime._sha256_bytes(raw)
        if expected_sha256.lower() != source_hash:
            raise ToolRuntimeError("STALE_CONTENT", "File đã thay đổi từ lúc agent đọc; hãy đọc lại trước khi đề xuất sửa.")
        original = raw.decode("utf-8-sig")
        without_crlf = original.replace("\r\n", "")
        normalize_crlf = "\r\n" in original and "\r" not in without_crlf and "\n" not in without_crlf

        spans = []
        for index, edit in enumerate(edits, 1):
            old_text = edit["old_text"]
            new_text = edit["new_text"]
            # read_file presents numbered lines joined by LF. Accept that
            # representation when the source has a single CRLF convention.
            if normalize_crlf:
                old_text = old_text.replace("\r\n", "\n").replace("\n", "\r\n")
                new_text = new_text.replace("\r\n", "\n").replace("\n", "\r\n")
            start = original.find(old_text)
            if start < 0:
                raise ToolRuntimeError("EDIT_NOT_FOUND", f"Không tìm thấy old_text của thay đổi {index}; cần khớp chính xác cả ký tự xuống dòng.")
            if original.find(old_text, start + 1) >= 0:
                raise ToolRuntimeError("AMBIGUOUS_EDIT", f"old_text của thay đổi {index} xuất hiện nhiều lần; hãy thêm ngữ cảnh để xác định duy nhất.")
            spans.append((start, start + len(old_text), new_text))

        spans.sort(key=lambda span: span[0])
        previous_end = 0
        pieces = []
        for start, end, replacement in spans:
            if start < previous_end:
                raise ToolRuntimeError("OVERLAPPING_EDITS", "Các thay đổi chồng lên nhau; hãy gộp thành một thay đổi rõ ràng.")
            pieces.extend((original[previous_end:start], replacement))
            previous_end = end
        pieces.append(original[previous_end:])
        content = "".join(pieces)
        if content == original:
            raise ToolRuntimeError("NO_CHANGE", "Các thay đổi không làm thay đổi nội dung file.")
        # apply_write encodes as UTF-8 with newline="". Keep the original BOM
        # explicitly and leave every untouched newline byte unchanged.
        if raw.startswith(codecs.BOM_UTF8):
            content = "\ufeff" + content
        if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
            raise ToolRuntimeError("TOO_LARGE", f"Nội dung vượt giới hạn ghi {MAX_WRITE_BYTES // 1024} KB.")

        result = runtime.propose_write_file(
            path=relative.as_posix(),
            content=content,
            expected_sha256=source_hash,
            description=description,
        )
        if result.ok:
            result.data["edit_count"] = len(edits)
            result.data["original_sha256"] = source_hash
            result.data["newline_handling"] = "normalized_to_crlf" if normalize_crlf else "exact"
        return result
    except ToolRuntimeError as exc:
        return ToolResult(False, error=exc.message, error_code=exc.code)
    except UnicodeError:
        return ToolResult(False, error="File và thay đổi phải là văn bản UTF-8 hợp lệ.", error_code="INVALID_ENCODING")
    except OSError as exc:
        return ToolResult(False, error=str(exc), error_code="EDIT_PROPOSAL_FAILED")
