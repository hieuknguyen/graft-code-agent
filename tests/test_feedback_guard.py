"""Regression coverage for no-progress terminal feedback and queued retries."""

import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from config import AppConfig
from core.feedback_guard import FeedbackLoopGuard
from core.session_manager import SessionManager
from desktop.main_window import MainWindow


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


def test_repeated_command_stops_after_four_without_progress():
    guard = FeedbackLoopGuard()
    for command in ["pytest tests/", "  pytest  tests/ ", "pytest tests/"]:
        assert guard.observe(command, 0) is None
    assert guard.observe("pytest tests/", 0)
    # Once tripped, a different retry cannot restart the same task.
    assert guard.observe("python -m pytest", 0)


def test_alternating_commands_cannot_evade_guard():
    guard = FeedbackLoopGuard()
    for command in ["pytest", "python -m compileall ."] * 3:
        assert guard.observe(command, 0) is None
    assert guard.observe("pytest", 0)


def test_equivalent_full_file_reads_share_history():
    guard = FeedbackLoopGuard()
    commands = [
        "type main.py",
        'powershell -NoProfile -Command "Get-Content -Path \'main.py\' -Encoding UTF8"',
        'python -c "with open(\'main.py\', encoding=\'utf-8\') as f: print(f.read())"',
        'python -c "from pathlib import Path; print(Path(\'./main.py\').read_text())"',
    ]
    for command in commands[:-1]:
        assert guard.observe(command, 0) is None
    assert guard.observe(commands[-1], 0)


def test_distinct_reads_and_ranges_remain_productive():
    guard = FeedbackLoopGuard()
    for index in range(50):
        assert guard.observe(f"type module_{index}.py", 0) is None
        assert guard.observe(f"Get-Content main.py -Tail {index + 1}", 0) is None
        assert guard.observe(f'python -c "print(open(\'main.py\').read()[{index}:])"', 0) is None


def test_different_assertions_and_transforms_do_not_count_as_the_same_read():
    guard = FeedbackLoopGuard()
    for index in range(20):
        assert guard.observe(
            f'python -c "from pathlib import Path; assert \'feature_{index}\' in Path(\'main.py\').read_text()"', 0,
        ) is None
        assert guard.observe(
            f'powershell -Command "Get-Content main.py; Write-Output {index}"', 0,
        ) is None
        assert guard.observe(
            f'python -c "f = open(\'main.py\'); f.seek({index}); print(f.read())"', 0,
        ) is None


def test_bare_path_powershell_wrapper_matches_full_file_read():
    guard = FeedbackLoopGuard()
    for command in ["type main.py", 'powershell -Command "Get-Content main.py"', "Get-Content 'main.py' -Raw"]:
        assert guard.observe(command, 0) is None
    assert guard.observe('python -c "print(open(\'main.py\').read())"', 0)


def test_progress_and_new_task_reset_history():
    guard = FeedbackLoopGuard()
    for revision in range(30):
        for _ in range(3):
            assert guard.observe("pytest", revision) is None
    assert guard.observe("pytest", 29)
    guard.reset(0)
    assert guard.observe("pytest", 0) is None


def test_unlimited_feedback_stops_and_invalidates_delayed_callbacks(window):
    generation = window._automation_generation
    with patch("desktop.main_window.AgentFeedbackWorker") as worker, \
         patch("desktop.main_window.QTimer.singleShot") as timer, \
         patch.object(window, "run_terminal_command") as run:
        window._schedule_automatic_command("pytest", 600)
        pending_callback = timer.call_args.args[1]
        for _ in range(4):
            window.start_agent_feedback_step("pytest", 1, "SyntaxError: invalid syntax")
        assert worker.call_count == 3
        assert window.feedback_loop_count == 3
        assert window.feedback_loop_active is False
        assert window._automation_generation > generation
        # Even a subsequent request cannot make a timer from this task current.
        window.feedback_loop_active = True
        pending_callback()
        run.assert_not_called()


def test_successful_queued_commands_are_guarded_too(window):
    window.command_queue = ["type main.py"] * 10
    with patch.object(window, "_schedule_automatic_command") as schedule:
        for _ in range(4):
            window.on_command_completed("type main.py", 0, "file contents")
    assert schedule.call_count == 3
    assert window.feedback_loop_active is False
    assert window.command_queue == []


def test_real_content_change_resets_guard_but_identical_write_does_not(window):
    with patch("desktop.main_window.AgentFeedbackWorker"):
        for _ in range(3):
            window.start_agent_feedback_step("pytest", 1, "failed")
        success, _ = window.agent.create_new_file("fixed.py", "answer = 1\n")
        assert success
        window.start_agent_feedback_step("pytest", 1, "failed")
        assert window.feedback_loop_active is True
        revision = window.agent.feedback_progress_revision
        for _ in range(3):
            success, _ = window.agent.create_new_file("fixed.py", "answer = 1\n")
            assert success
            assert window.agent.feedback_progress_revision == revision
            window.start_agent_feedback_step("pytest", 1, "failed")
    assert window.feedback_loop_active is False


def test_new_user_request_resets_agent_and_guard(window):
    for _ in range(4):
        window.feedback_guard.observe("pytest", 0)
    window.agent.create_new_file("old.py", "old = True\n")
    with patch("desktop.main_window.GraftWorker"), \
         patch.object(window.agent, "begin_task", wraps=window.agent.begin_task) as begin:
        window.on_graft_requested("Fix a different issue", "", {})
    begin.assert_called_once_with()
    assert window.feedback_loop_count == 0
    assert window.agent.feedback_progress_revision == 0
    assert window.feedback_guard.observe("pytest", 0) is None


@pytest.mark.parametrize("success", [False, True])
def test_failed_or_unchanged_patch_does_not_trigger_automatic_retry(window, success):
    window.process_runner.current_cmd = "pytest"
    with patch.object(window.agent, "apply_action", return_value=(success, "No disk change")), \
         patch.object(window, "update_codebase_views"), \
         patch.object(window, "_schedule_automatic_command") as schedule:
        window.on_feedback_finished({
            "success": True,
            "actions": [{"success": True, "file": "main.py"}],
        })
    schedule.assert_not_called()
    assert window.feedback_loop_active is False
