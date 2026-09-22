"""Exercise Windows shell parsing through the real QProcess launch path."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QProcessEnvironment
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from core.process_runner import ProcessRunner


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows shell regression tests")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def project(tmp_path):
    directory = tmp_path / "project with spaces & brackets (test)"
    directory.mkdir()
    (directory / "sample file.txt").write_text("file contents preserved", encoding="utf-8")
    (directory / "config.py").write_text("VALUE = 7\n", encoding="utf-8")
    (directory / "local tool.cmd").write_text("@echo batch-works\n", encoding="utf-8")
    return directory


def run_command(runner, command, project, shell="cmd"):
    environment = QProcessEnvironment.systemEnvironment()
    environment.insert("PATH", str(Path(sys.executable).parent) + os.pathsep + environment.value("PATH"))
    runner.process.setProcessEnvironment(environment)
    output = []
    collect_output = lambda text, is_error: output.append(text)
    runner.output_received.connect(collect_output)
    finished = QSignalSpy(runner.command_completed)
    try:
        assert runner.run_command(command, project, shell=shell)
        assert runner.process.waitForStarted(5000), runner.full_log
        if runner.is_running():
            assert runner.process.waitForFinished(15000), runner.full_log
        assert finished.count() == 1, runner.full_log
        assert finished.at(0)[1] == 0, runner.full_log
        return "".join(output)
    finally:
        runner.output_received.disconnect(collect_output)
        if runner.is_running():
            runner.kill_process()


@pytest.mark.parametrize("command,expected", [
    (
        'python.exe -c "import config; print(\'Imports verified: %s\' % config.VALUE)"',
        "Imports verified: 7",
    ),
    (
        f'"{sys.executable}" -c "import config; print(\'Imports verified: %s\' % config.VALUE)"',
        "Imports verified: 7",
    ),
    (
        f'"{sys.executable}" -c "from pathlib import Path; print(Path(\'sample file.txt\').read_text())"',
        "file contents preserved",
    ),
    ('type "sample file.txt" && echo chain-finished', "file contents preservedchain-finished"),
    ('"local tool.cmd"', "batch-works"),
    ('echo literal^&ampersand', "literal&ampersand"),
    (
        'powershell -NoProfile -NonInteractive -Command "Get-Content -LiteralPath \'sample file.txt\'"',
        "file contents preserved",
    ),
])
def test_cmd_preserves_nested_quotes_and_shell_operators(app, project, command, expected):
    runner = ProcessRunner()
    output = run_command(runner, command, project)
    assert expected in output.splitlines()


@pytest.mark.parametrize("command,expected", [
    ('Write-Output "quoted text"', "quoted text"),
    ('$value = "value"; Write-Output "$value $(1 + 2)"', "value 3"),
    ('Get-Content -LiteralPath "sample file.txt"', "file contents preserved"),
])
def test_powershell_preserves_its_own_quoting(app, project, command, expected):
    runner = ProcessRunner()
    output = run_command(runner, command, project, shell="powershell")
    assert expected in output.splitlines()


def test_switching_shells_clears_previous_native_arguments(app, project):
    runner = ProcessRunner()
    run_command(runner, "echo from-cmd", project)
    output = run_command(runner, 'Write-Output "from-powershell"', project, shell="powershell")
    assert "from-powershell" in output.splitlines()
    output = run_command(runner, "echo back-to-cmd", project)
    assert "back-to-cmd" in output.splitlines()
