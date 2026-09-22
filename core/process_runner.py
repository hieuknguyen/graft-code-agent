"""Run terminal commands for the desktop UI without managing unrelated processes."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QObject, QProcess, Signal


_SERVER_URL_RE = re.compile(r"(https?://(?:127\.0\.0\.1|localhost|0\.0\.0\.0):[0-9]+)")
_SUPPORTED_SHELLS = frozenset({"cmd", "powershell"})


class ProcessRunner(QObject):
    """Execute one user-requested command and stream its output through Qt signals.

    The runner intentionally manages only the ``QProcess`` that it starts. It does
    not scan for ports or terminate external processes, because those actions can
    affect applications outside the active workspace.
    """

    output_received = Signal(str, bool)  # text, is_error
    process_started = Signal(str)
    process_finished = Signal(int)
    command_completed = Signal(str, int, str)  # command, exit_code, full_log
    server_detected = Signal(str, str)  # command, server_url

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.started.connect(self._on_started)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_process_error)

        self.current_cmd = ""
        # Kept as a public attribute so callers can show the selected shell.
        self.current_shell = "cmd"
        # Metadata for the current/most recently launched command. UI consumers
        # may read this without parsing display text or the command itself.
        self.command_metadata: dict[str, Any] = {}
        self.full_log = ""
        self.server_notified = False
        self.suppress_completion_signal = False

    @staticmethod
    def free_port(port: int) -> bool:
        """Deprecated compatibility no-op.

        Earlier versions searched the host for listeners and stopped them. Keeping
        this method as a no-op avoids breaking callers while ensuring a command can
        never affect an unrelated process merely because it uses the same port.
        """

        del port
        return False

    def run_command(
        self,
        command: str,
        cwd: str | os.PathLike[str],
        auto_kill_running: bool = True,
        shell: Optional[str] = "cmd",
    ) -> bool:
        """Start ``command`` in ``cwd`` using ``cmd`` or ``powershell`` on Windows.

        ``shell`` defaults to ``cmd`` to preserve the existing terminal UI and its
        command syntax. On non-Windows hosts the existing ``/bin/sh`` fallback is
        retained, while metadata still records the requested Windows shell mode.
        Returns ``True`` once Qt has accepted the start request, or ``False`` when
        validation fails or an active process cannot be stopped safely.
        """

        try:
            normalized_shell = self._normalize_shell(shell)
            working_directory = self._validated_working_directory(cwd)
            self._validate_command(command)
        except ValueError as exc:
            self._report_launch_error(str(exc))
            return False

        # Validate everything before stopping a live process. A typo in a new
        # command or working directory must not interrupt the user's current task.
        if self.is_running():
            if not auto_kill_running:
                self._report_launch_error(
                    "Một tiến trình khác đang chạy. Vui lòng dừng tiến trình trước."
                )
                return False

            old_cmd = self.current_cmd
            self.output_received.emit(
                f"\n🔄 [DỪNG TIẾN TRÌNH CŨ ĐỂ CHẠY LỆNH MỚI]: {old_cmd}\n", False
            )
            if not self.kill_process(silent_for_restart=True):
                self._report_launch_error(
                    "Không thể dừng tiến trình hiện tại; lệnh mới chưa được khởi chạy."
                )
                return False

        program, arguments = self._build_invocation(normalized_shell, command)
        native_arguments = ""
        if os.name == "nt" and program == "cmd.exe":
            # QProcess quotes argument lists for CommandLineToArgvW, but CMD
            # uses different rules: the inserted backslashes corrupt quotes in
            # python -c, paths, and nested PowerShell commands. Pass its command
            # line verbatim, with one outer quote pair consumed by /s /c.
            # https://doc.qt.io/qt-6/qprocess.html#setNativeArguments
            native_arguments = " ".join(arguments[:-1]) + f' "{arguments[-1]}"'
            arguments = []

        self.current_cmd = command
        self.current_shell = normalized_shell
        self.full_log = ""
        self.server_notified = False
        self.suppress_completion_signal = False
        self.command_metadata = {
            "command": command,
            "cwd": str(working_directory),
            "shell": normalized_shell,
            "program": program,
            "arguments": list(arguments),
            "native_arguments": native_arguments,
            "started_at": None,
            "finished_at": None,
            "pid": None,
            "status": "starting",
            "exit_code": None,
        }

        self.process.setWorkingDirectory(str(working_directory))
        self.process.setProgram(program)
        self.process.setArguments(arguments)
        if os.name == "nt":
            # A QProcess is reused when switching shells. Never carry the last
            # CMD command into a later PowerShell (or direct program) invocation.
            self.process.setNativeArguments(native_arguments)
        self.process.start()
        return True

    @staticmethod
    def _normalize_shell(shell: Optional[str]) -> str:
        if shell is None:
            return "cmd"
        if not isinstance(shell, str):
            raise ValueError("Shell phải là 'cmd' hoặc 'powershell'.")

        normalized = shell.strip().lower()
        if normalized not in _SUPPORTED_SHELLS:
            raise ValueError("Shell không hợp lệ. Chỉ hỗ trợ 'cmd' hoặc 'powershell'.")
        return normalized

    @staticmethod
    def _validated_working_directory(cwd: str | os.PathLike[str]) -> Path:
        if cwd is None:
            raise ValueError("Không thể chạy lệnh: chưa chọn thư mục làm việc.")

        try:
            working_directory = Path(cwd).expanduser()
        except TypeError as exc:
            raise ValueError("Không thể chạy lệnh: thư mục làm việc không hợp lệ.") from exc

        if not working_directory.is_dir():
            raise ValueError(
                f"Không thể chạy lệnh: thư mục làm việc không tồn tại hoặc không phải thư mục: {cwd}"
            )
        return working_directory.resolve()

    @staticmethod
    def _validate_command(command: str) -> None:
        if not isinstance(command, str) or not command.strip():
            raise ValueError("Không thể chạy lệnh trống.")
        if "\x00" in command:
            raise ValueError("Không thể chạy lệnh chứa ký tự NUL.")

    @staticmethod
    def _build_invocation(shell: str, command: str) -> tuple[str, list[str]]:
        if os.name != "nt":
            # Preserve the previous cross-platform behavior. The desktop app is
            # Windows-oriented, but this makes tests and non-Windows development
            # environments continue to work without a Windows shell installed.
            return "/bin/sh", ["-c", command]

        if shell == "powershell":
            return "powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", command]

        # /d disables AutoRun commands, which prevents machine-local cmd startup
        # hooks from changing the behavior of a command run by the application.
        return "cmd.exe", ["/d", "/s", "/c", command]

    def _report_launch_error(self, message: str) -> None:
        self.output_received.emit(f"\n[!] {message}\n", True)

    def _on_started(self):
        self.command_metadata.update(
            {
                "started_at": time.time(),
                "pid": int(self.process.processId()),
                "status": "running",
            }
        )
        self.process_started.emit(self.current_cmd)
        msg = (
            f"\n🚀 [ĐANG CHẠY ({self.current_shell.upper()})]: {self.current_cmd}\n"
            "------------------------------------------------------------\n"
        )
        self.full_log += msg
        self.output_received.emit(msg, False)

    def _on_stdout(self):
        data = self.process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self.full_log += data
        self.output_received.emit(data, False)
        self._detect_server_url(data)

    def _on_stderr(self):
        data = self.process.readAllStandardError().data().decode("utf-8", errors="replace")
        self.full_log += data
        self.output_received.emit(data, True)
        self._detect_server_url(data)

    def _detect_server_url(self, data: str) -> None:
        if self.server_notified:
            return

        match = _SERVER_URL_RE.search(data)
        if match:
            self.server_notified = True
            self.server_detected.emit(self.current_cmd, match.group(1))

    def _on_process_error(self, error: QProcess.ProcessError) -> None:
        # A crash is followed by ``finished`` and gets its normal completion log.
        # Other errors (notably a missing shell executable) may not emit it.
        if error == QProcess.ProcessError.Crashed:
            return

        error_text = self.process.errorString() or "Lỗi không xác định khi khởi chạy tiến trình."
        self.command_metadata.update({"status": "error", "error": error_text})
        msg = f"\n[!] KHÔNG THỂ KHỞI CHẠY TIẾN TRÌNH: {error_text}\n"
        self.full_log += msg
        self.output_received.emit(msg, True)

    def _on_finished(self, exit_code: int):
        self.command_metadata.update(
            {
                "finished_at": time.time(),
                "status": "finished",
                "exit_code": exit_code,
            }
        )
        self.process_finished.emit(exit_code)
        status_text = "THÀNH CÔNG" if exit_code == 0 else f"LỖI (Exit Code: {exit_code})"
        end_msg = (
            "\n------------------------------------------------------------\n"
            f"🏁 [TIẾN TRÌNH KẾT THÚC]: {status_text}\n"
        )
        self.full_log += end_msg
        self.output_received.emit(end_msg, exit_code != 0)

        if self.suppress_completion_signal:
            self.suppress_completion_signal = False
            return

        self.command_completed.emit(self.current_cmd, exit_code, self.full_log)

    def is_running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def write_stdin(self, text: str):
        if self.is_running():
            self.process.write(text.encode("utf-8") + b"\n")
            self.full_log += f"{text}\n"
            self.output_received.emit(f"{text}\n", False)

    def kill_process(self, silent_for_restart: bool = False) -> bool:
        """Stop only the ``QProcess`` owned by this runner.

        A graceful terminate is attempted first, then Qt's process kill is used as
        a bounded fallback. Descendant processes are deliberately not searched for
        or terminated outside this direct process relationship.
        """

        if not self.is_running():
            return True

        self.suppress_completion_signal = silent_for_restart
        self.process.terminate()
        if not self.process.waitForFinished(1000):
            self.process.kill()
            if not self.process.waitForFinished(1000):
                self.suppress_completion_signal = False
                self.command_metadata.update({"status": "stop_failed"})
                self._report_launch_error("Không thể dừng tiến trình hiện tại.")
                return False

        self.command_metadata["stopped_by_user"] = not silent_for_restart
        msg = (
            "\n🔄 [TIẾN TRÌNH CŨ ĐÃ ĐƯỢC DỪNG ĐỂ CHẠY LỆNH MỚI]\n"
            if silent_for_restart
            else "\n⚠️ [TIẾN TRÌNH ĐÃ BỊ DỪNG BỞI NGƯỜI DÙNG]\n"
        )
        self.full_log += msg
        self.output_received.emit(msg, True)
        return True
