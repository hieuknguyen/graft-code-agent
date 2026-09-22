"""A completed or stopped app must not be reopened by automatic follow-up."""

import os
import sys
import time
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QProcess
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from config import AppConfig
from core.agent import GraftAgent
from core.session_manager import SessionManager
from desktop.main_window import MainWindow
from desktop.threads import AgentFeedbackWorker


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    with patch("desktop.main_window.SessionManager", return_value=SessionManager(str(tmp_path / "history"))), \
         patch("desktop.main_window.load_config", return_value=AppConfig(max_feedback_loops=0)), \
         patch.object(MainWindow, "initial_setup"):
        widget = MainWindow(str(project))
        widget.feedback_loop_active = True
        widget.prompt.chk_feedback.setChecked(True)
        yield widget
        widget.on_stop_process_requested()
        widget.close()
        widget.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("language", ["bash", "sh", "shell", "cmd", "powershell"])
def test_reuse_instructions_do_not_become_commands(tmp_path, language):
    agent = GraftAgent(AppConfig(), str(tmp_path))
    response = (
        "The chart session has finished. To view it again later, run:\n"
        f"```{language}\npython plot_btc_weekly.py\n```\n"
    )
    assert agent.parse_all_actions(response)["command"] == []
    assert "python plot_btc_weekly.py" in agent.clean_ai_response(response)


def test_only_explicit_run_command_is_queued(tmp_path):
    agent = GraftAgent(AppConfig(), str(tmp_path))
    response = """Run the focused check now:
<<<RUN_COMMAND
Command: python -m pytest tests/test_chart.py
Description: Verify chart behavior.
<<<END_RUN_COMMAND
To reopen the application later:
```bash
python plot_btc_weekly.py
```
"""
    assert agent.parse_all_actions(response)["command"] == [{
        "command": "python -m pytest tests/test_chart.py",
        "description": "Verify chart behavior.",
    }]


@pytest.mark.parametrize("max_loops", [0, 6])
@pytest.mark.parametrize("command", [
    "python plot_btc_weekly.py",
    '"C:\\my directory\\python.exe" -u "charts\\weekly chart.py"',
    'pythonw.exe "charts\\weekly chart.pyw"',
    "node index.js",
    "npm start",
])
def test_successful_app_exit_stops_feedback_even_in_unlimited_mode(window, max_loops, command):
    window.max_feedback_loops = max_loops
    with patch.object(window, "start_agent_feedback_step") as feedback, \
         patch.object(window, "run_terminal_command") as run:
        window.on_command_completed(command, 0, "Chart displayed.\n")
    feedback.assert_not_called()
    run.assert_not_called()
    assert window.feedback_loop_active is False
    assert window.command_queue == []


@pytest.mark.parametrize("command", [
    "python -m pip install matplotlib",
    "python -m pytest tests/test_chart.py",
    "python -m unittest tests.test_chart",
    "type main.py",
])
def test_helper_commands_still_receive_feedback(window, command):
    with patch.object(window, "start_agent_feedback_step") as feedback:
        window.on_command_completed(command, 0, "Completed successfully")
    feedback.assert_called_once_with(command, 0, "Completed successfully")
    assert window.feedback_loop_active is True


@pytest.mark.parametrize("exit_code, output", [
    (1, "Application failed"),
    (0, "Traceback (most recent call last):\nRuntimeError: chart failed"),
])
def test_failed_app_is_still_diagnosed(window, exit_code, output):
    with patch.object(window, "start_agent_feedback_step") as feedback:
        window.on_command_completed("python plot_btc_weekly.py", exit_code, output)
    feedback.assert_called_once_with("python plot_btc_weekly.py", exit_code, output)


def test_failed_prerequisite_does_not_launch_queued_app(window):
    window.command_queue = ["python plot_btc_weekly.py"]
    with patch.object(window, "start_agent_feedback_step") as feedback, \
         patch.object(window, "_schedule_automatic_command") as schedule:
        window.on_command_completed("python -m pip install matplotlib", 1, "Install failed")
    schedule.assert_not_called()
    feedback.assert_called_once()
    assert window.command_queue == []


def test_stop_cancels_delayed_command_even_if_new_work_starts(window):
    with patch("desktop.main_window.QTimer.singleShot") as timer, \
         patch.object(window, "run_terminal_command") as run:
        window._schedule_automatic_command("python plot_btc_weekly.py", 800)
        delayed_command = timer.call_args.args[1]
        window.on_stop_process_requested()
        window.feedback_loop_active = True  # A new request must not revive the old timer.
        delayed_command()
    run.assert_not_called()


def test_active_delayed_command_runs_normally(window):
    with patch("desktop.main_window.QTimer.singleShot") as timer, \
         patch.object(window, "run_terminal_command") as run:
        window._schedule_automatic_command("python plot_btc_weekly.py", 600)
        timer.call_args.args[1]()
    run.assert_called_once_with("python plot_btc_weekly.py")


def test_late_feedback_cannot_restart_or_edit_after_stop(window):
    window.on_stop_process_requested()
    with patch.object(window, "_schedule_automatic_command") as schedule, \
         patch.object(window.agent, "apply_action") as apply, \
         patch.object(window.agent, "create_new_file") as create:
        window.on_feedback_finished({
            "success": True,
            "commands": [{"command": "python plot_btc_weekly.py"}],
            "actions": [{"success": True, "file": "plot_btc_weekly.py"}],
            "create_files": [{"file": "extra.py", "code": "print('extra')"}],
        })
    schedule.assert_not_called()
    apply.assert_not_called()
    create.assert_not_called()
    assert window.feedback_loop_active is False


def test_old_feedback_is_ignored_after_a_new_request_starts(window):
    worker = AgentFeedbackWorker(window.agent, "old task", "python chart.py", 1, "Failed")
    worker.automation_generation = window._automation_generation
    worker.finished.connect(window.on_feedback_finished)
    worker.error.connect(window.on_feedback_error)
    window.on_stop_process_requested()
    window.feedback_loop_active = True
    with patch.object(window, "_schedule_automatic_command") as schedule:
        worker.finished.emit({"success": True, "commands": [{"command": "python chart.py"}]})
        worker.error.emit("Error from an old request")
    schedule.assert_not_called()
    assert window.feedback_loop_active is True


def test_current_feedback_can_schedule_a_repair(window):
    worker = AgentFeedbackWorker(window.agent, "fix chart", "python chart.py", 1, "Failed")
    worker.automation_generation = window._automation_generation
    worker.finished.connect(window.on_feedback_finished)
    with patch.object(window, "_schedule_automatic_command") as schedule:
        worker.finished.emit({"success": True, "commands": [{"command": "python chart.py"}]})
    schedule.assert_called_once_with("python chart.py", 800)


def test_late_health_probe_cannot_reactivate_stopped_session(window):
    command = "python -m http.server"
    generation = window._automation_generation
    window.process_runner.current_cmd = command
    window.on_stop_process_requested()
    with patch.object(window.process_runner, "is_running", return_value=True), \
         patch.object(window, "start_agent_feedback_step") as feedback:
        window.on_probe_finished(command, "http://localhost:8000", {
            "is_healthy": False, "error": "Connection refused",
        }, generation)
    feedback.assert_not_called()
    assert window.feedback_loop_active is False


def test_closing_real_gui_does_not_request_another_run(window, app):
    # The child runs offscreen and closes its own window, reproducing the same
    # normal process completion as clicking Close without showing a desktop window.
    script = os.path.join(window.root_dir, "chart.py")
    with open(script, "w", encoding="utf-8") as handle:
        handle.write(
            "from PySide6.QtCore import QTimer\n"
            "from PySide6.QtWidgets import QApplication, QWidget\n"
            "app = QApplication([])\n"
            "window = QWidget()\n"
            "window.show()\n"
            "QTimer.singleShot(100, window.close)\n"
            "app.exec()\n"
        )
    completed = QSignalSpy(window.process_runner.command_completed)
    # Invoke Python directly so this checks process/window lifecycle independently
    # of each host shell's command-line quoting rules.
    with patch.object(window, "start_agent_feedback_step") as feedback, \
         patch.object(window.process_runner, "_build_invocation", return_value=(sys.executable, [script])):
        window.run_terminal_command(f'"{sys.executable}" "{script}"')
        deadline = time.monotonic() + 10
        while not completed.count() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert completed.count() == 1, window.process_runner.full_log
        assert completed.at(0)[1] == 0, window.process_runner.full_log
        feedback.assert_not_called()
    assert window.feedback_loop_active is False
    assert window.process_runner.process.state() == QProcess.ProcessState.NotRunning
