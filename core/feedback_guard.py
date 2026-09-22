"""Detect terminal retries that make no progress without limiting useful work."""

from __future__ import annotations

import ast
from collections import deque
import os
import re


class FeedbackLoopGuard:
    """A bounded, per-task circuit breaker independent of the configured step cap.

    Only successful changes to file contents reset the retry history. A proposed
    patch, failed write, or re-applying identical contents is not progress. Commands
    with different identities can continue indefinitely, including long test queues.
    """

    def __init__(self, repeat_limit: int = 4, window_size: int = 12):
        self.repeat_limit = repeat_limit
        self._recent = deque(maxlen=max(window_size, repeat_limit))
        self.reset()

    def reset(self, progress_revision: int = 0) -> None:
        self._revision = progress_revision
        self._recent.clear()
        self._stop_reason = None

    def observe(self, command: str, progress_revision: int) -> str | None:
        if progress_revision != self._revision:
            self.reset(progress_revision)
        if self._stop_reason:
            return self._stop_reason

        identity = self._command_identity(command)
        self._recent.append(identity)
        if self._recent.count(identity) >= self.repeat_limit:
            self._stop_reason = (
                f"Cùng một lệnh hoặc thao tác đọc file đã lặp lại {self.repeat_limit} lần "
                "mà không có thay đổi nội dung file thành công. "
                "Đã dừng hàng đợi và vòng lặp tự động. "
                "Bạn có thể kiểm tra log rồi gửi yêu cầu mới để tiếp tục."
            )
        return self._stop_reason

    @staticmethod
    def _command_identity(command: str) -> str:
        # Recognize only full-file reads. Distinct ranges and pipelines may read
        # new information and must retain their complete command identity.
        path = None
        simple_read = re.fullmatch(
            r"\s*(?:type|cat)\s+(?:\"([^\"]+)\"|'([^']+)'|([^\s;&|<>]+))\s*",
            command, re.IGNORECASE,
        )
        if simple_read:
            path = next(part for part in simple_read.groups() if part is not None)
        else:
            shell_wrapper = re.fullmatch(
                r'''\s*(?:powershell|pwsh)(?:\.exe)?\s+(?:(?:-NoProfile|-NonInteractive|-NoLogo)\s+)*-Command\s+(["'])(.*)\1\s*''',
                command, re.IGNORECASE | re.DOTALL,
            )
            shell_body = shell_wrapper.group(2) if shell_wrapper else command
            powershell_read = re.fullmatch(
                r"\s*Get-Content\s+(?:-Raw\s+)?(?:(?:-LiteralPath|-Path)\s+)?"
                r"(?:'([^']+)'|\"([^\"]+)\"|([^\s;'\"`|&<>]+))"
                r"(?:\s+(?:-Encoding\s+[\w-]+|-Raw))*\s*",
                shell_body, re.IGNORECASE,
            )
            if powershell_read:
                path = next(part for part in powershell_read.groups() if part is not None)
            else:
                path = FeedbackLoopGuard._python_printed_file(command)

        if path:
            # Windows paths can be spelled with either slash, quotes, or './'.
            path = os.path.normcase(os.path.normpath(path.replace("\\", "/")))
            return "read-file:" + path
        # Preserve quoted strings: spaces inside script literals can be meaningful.
        tokens = re.findall(r'''"[^"\n]*"|'[^'\n]*'|[^\s]+''', command.strip())
        return "command:" + " ".join(tokens)

    @staticmethod
    def _python_printed_file(command: str) -> str | None:
        """Match pure ``print(file.read())`` scripts, never assertions/transforms."""
        inline = re.fullmatch(
            r'''\s*(?:python(?:\d+(?:\.\d+)?)?|py)(?:\.exe)?\s+-c\s+(["'])(.*)\1\s*''',
            command, re.DOTALL,
        )
        if not inline:
            return None
        try:
            statements = ast.parse(inline.group(2)).body
        except (SyntaxError, ValueError):
            return None
        if statements and isinstance(statements[0], ast.ImportFrom):
            imported = statements[0]
            if imported.module == "pathlib" and len(imported.names) == 1 and imported.names[0].name == "Path" and imported.names[0].asname is None:
                statements = statements[1:]
        if len(statements) != 1:
            return None
        statement = statements[0]
        opened_file = None
        binding = None
        if isinstance(statement, ast.With) and len(statement.items) == 1 and len(statement.body) == 1:
            opened_file = statement.items[0].context_expr
            binding = statement.items[0].optional_vars
            statement = statement.body[0]
        if not isinstance(statement, ast.Expr):
            return None
        printed = statement.value
        if not isinstance(printed, ast.Call) or not isinstance(printed.func, ast.Name) or printed.func.id != "print" or len(printed.args) != 1 or printed.keywords:
            return None
        read = printed.args[0]
        if not isinstance(read, ast.Call) or not isinstance(read.func, ast.Attribute) or read.func.attr not in {"read", "read_text", "read_bytes"} or read.args:
            return None
        if any(keyword.arg not in {"encoding", "errors"} or not isinstance(keyword.value, ast.Constant) for keyword in read.keywords):
            return None
        if opened_file is not None:
            if not isinstance(binding, ast.Name) or not isinstance(read.func.value, ast.Name) or binding.id != read.func.value.id:
                return None
        else:
            opened_file = read.func.value
        if not isinstance(opened_file, ast.Call) or not isinstance(opened_file.func, ast.Name) or opened_file.func.id not in {"open", "Path"} or len(opened_file.args) != 1:
            return None
        if any(keyword.arg not in {"encoding", "errors"} or not isinstance(keyword.value, ast.Constant) for keyword in opened_file.keywords):
            return None
        path = opened_file.args[0]
        return path.value if isinstance(path, ast.Constant) and isinstance(path.value, str) else None
