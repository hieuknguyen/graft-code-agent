"""Exercise the desktop's rearranged surfaces without contacting an AI API."""

import os
import time
from threading import Event
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt, QThread, QUrl
from PySide6.QtGui import QImage
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from config import AppConfig
from core.agent import GraftAgent
from core.session_manager import SessionManager
from desktop.main_window import MainWindow
from desktop.views.prompt_widget import PromptWidget


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setStyle("Fusion")
    return instance


@pytest.fixture
def window(app, tmp_path):
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "src" / "example.py").write_text(
        "# Example\n\ndef greet(name):\n    return f'Hello {name}'\n", encoding="utf-8"
    )
    with patch("desktop.main_window.SessionManager", return_value=SessionManager(str(tmp_path / "history"))), \
         patch("desktop.main_window.load_config", return_value=AppConfig()), \
         patch.object(MainWindow, "initial_setup"):
        widget = MainWindow(str(project))
        widget.agent.scan()
        widget.update_codebase_views()
        widget.show()
        app.processEvents()
        yield widget
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_file_symbol_and_diff_keep_agent_visible(window, app):
    folder = window.sidebar.tree.topLevelItem(0)
    file_item = folder.child(0)
    symbol = file_item.child(0)
    window.sidebar.tree.itemClicked.emit(file_item, 0)
    app.processEvents()
    assert window.editor.current_file == "src/example.py"
    assert "def greet(name)" in window.editor.code_editor.toPlainText()
    assert window.editor.agent_panel.isVisible()
    assert not window.editor.terminal_view.isVisible()
    window.sidebar.tree.itemDoubleClicked.emit(symbol, 0)
    assert window.editor.code_editor.textCursor().blockNumber() == 2

    window.last_actions = [{"file": "src/example.py", "success": True,
                            "diff": "--- old\n+++ new\n-return 'hi'\n+return 'hello'"}]
    window.editor.chat_view.on_link_clicked(QUrl("graftview:///src/example.py"))
    assert window.editor.tabs.currentWidget() is window.editor.diff_viewer_tab
    assert "+return 'hello'" in window.editor.diff_browser.toPlainText()
    assert window.prompt.isVisible()

    window.sidebar.file_search.setText("greet")
    assert not folder.isHidden() and not file_item.isHidden() and not symbol.isHidden()
    window.sidebar.file_search.setText("missing-symbol")
    assert folder.isHidden()
    window.sidebar.file_search.clear()
    assert not folder.isHidden()


def test_compact_layout_navigation_and_options(window, app):
    window.resize(1000, 660)
    app.processEvents()
    assert window.width() == 1000
    window.prompt.btn_options.click()
    app.processEvents()
    assert window.prompt.options_panel.isVisible()
    for button in (window.prompt.btn_graft, window.prompt.btn_apply, window.prompt.btn_undo):
        assert button.isVisible()
        assert window.rect().contains(button.mapTo(window, button.rect().bottomRight()))
    assert not window.prompt.chk_auto.isChecked()
    window.editor.show_code()
    window.toggle_agent()
    assert not window.editor.workspace.isVisible()
    window.focus_agent()
    assert window.editor.agent_panel.isVisible()
    assert window.prompt.prompt_edit.hasFocus()
    window.toggle_terminal()
    assert window.editor.terminal_view.isVisible()
    window.toggle_terminal()
    assert not window.editor.terminal_view.isVisible()
    window.editor.show_terminal()
    assert window.editor.terminal_view.isVisible()
    window.show_sidebar_tab(0)
    assert window.sidebar.tabs.currentIndex() == 0
    window.focus_file_search()
    assert window.sidebar.tabs.currentIndex() == 1
    assert window.sidebar.file_search.hasFocus()


def test_home_composer_centers_then_docks_for_messages(window, app):
    assert not window.editor.workspace.isVisible()
    assert not window.editor.terminal_view.isVisible()
    assert not window.editor.chat_view.isVisible()
    assert not window.prompt.actions_panel.isVisible()
    center_y = window.editor.agent_panel.mapTo(window, window.editor.agent_panel.rect().center()).y()
    prompt_y = window.prompt.mapTo(window, window.prompt.rect().center()).y()
    assert abs(prompt_y - center_y) < 80
    window.editor.chat_view.add_user_message("Explain the project", persist=False)
    app.processEvents()
    assert window.editor.chat_view.isVisible()
    assert window.prompt.mapTo(window, window.prompt.rect().center()).y() > center_y + 100
    window.prompt.btn_apply.setEnabled(True)
    app.processEvents()
    assert window.prompt.btn_apply.isVisible()
    window.prompt.btn_apply.setEnabled(False)
    window.editor.chat_view.clear_chat()
    app.processEvents()
    assert not window.editor.chat_view.isVisible()
    assert abs(window.prompt.mapTo(window, window.prompt.rect().center()).y() - center_y) < 80


def test_grouped_history_opens_conversation_in_its_project(window, app, tmp_path):
    other = tmp_path / "other-project"
    other.mkdir()
    project = window.session_mgr.get_or_create_project(str(other))
    conversation = window.session_mgr.create_conversation(project["id"], "Review checkout")
    window.session_mgr.append_message(project["id"], conversation["id"], {
        "role": "user", "text": "Review the checkout flow"
    })
    window.sidebar.reload_projects_list(window.root_dir)
    tree = window.sidebar.projects_tree
    project_item = next(tree.topLevelItem(i) for i in range(tree.topLevelItemCount())
                        if tree.topLevelItem(i).text(0) == "other-project")
    window.sidebar.conv_search.setText("checkout")
    assert not project_item.isHidden()
    assert not project_item.child(0).isHidden()
    with patch.object(window, "do_scan"):
        tree.itemClicked.emit(project_item.child(0), 0)
    app.processEvents()
    assert window.root_dir == str(other)
    assert window.current_conv_id == conversation["id"]
    assert "Review the checkout flow" in window.editor.chat_view.browser.toPlainText()
    assert window.editor.chat_view.isVisible()
    assert "other-project" in window.workspace_button.text()


def test_prompt_keeps_target_images_and_blocks_duplicate_submission(app):
    prompt = PromptWidget()
    prompt.show()
    prompt.update_file_list(["src/example.py"])
    prompt.target_file_combo.setCurrentIndex(1)
    prompt.update_file_list(["another.py", "src/example.py"])
    prompt.prompt_edit.setPlainText("Review this function")
    image = QImage(16, 16, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.blue)
    prompt.add_qimage(image)
    received = QSignalSpy(prompt.graft_requested)
    QTest.keyClick(prompt.prompt_edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert received.count() == 1
    task, target, options = received.at(0)
    assert task == "Review this function"
    assert target == "src/example.py"
    assert options["images"][0].startswith("data:image/png;base64,")
    assert options["thinking"] and not options["auto_apply"]
    assert not prompt.attached_images and prompt.prompt_edit.toPlainText() == ""
    prompt.btn_graft.setEnabled(False)
    prompt.prompt_edit.setPlainText("Wait for the first request")
    QTest.keyClick(prompt.prompt_edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert received.count() == 1
    assert prompt.prompt_edit.toPlainText() == "Wait for the first request"
    prompt.close()


def test_terminal_keeps_command_and_stdin_routes(window):
    terminal = window.editor.terminal_view
    with patch.object(window.process_runner, "run_command") as run, \
         patch.object(window.process_runner, "is_running", return_value=False):
        terminal.cmd_input.setText("python --version")
        terminal.btn_run.click()
        run.assert_called_once_with("python --version", window.root_dir)
    received = QSignalSpy(terminal.stdin_requested)
    terminal.set_running(True)
    terminal.cmd_input.setText("yes")
    terminal.btn_run.click()
    assert received.at(0) == ["yes"]
    terminal.set_running(False)


def test_switch_workspace_resets_code_and_preserves_conversations(window, tmp_path):
    window.on_new_conversation_requested()
    original_project = window.current_project["id"]
    window.editor.chat_view.add_user_message("Explain this project")
    original_conv = window.current_conv_id
    window.on_file_selected("src/example.py")
    window.sidebar.file_search.setText("example")
    other = tmp_path / "other"
    other.mkdir()
    with patch.object(window, "do_scan"):
        window.switch_workspace(str(other))
    assert window.editor.current_file is None
    assert window.editor.pages.currentIndex() == 0
    assert "other" in window.workspace_button.text()
    assert window.sidebar.tree.topLevelItemCount() == 0
    assert window.sidebar.file_search.text() == ""
    assert window.prompt.target_file_combo.count() == 1
    assert window.prompt.target_file_combo.currentData() == ""
    saved = window.session_mgr.get_conversation(original_project, original_conv)
    assert saved["messages"][0]["text"] == "Explain this project"


def wait_until(app, condition):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(0.01)
    assert condition(), "Timed out waiting for the desktop scan"


@pytest.mark.parametrize("old_scan_fails", [False, True])
def test_switch_during_scan_loads_latest_project(window, app, tmp_path, old_scan_fails):
    old_agent = window.agent
    old_started, old_release = Event(), Event()
    new_started, new_release = Event(), Event()
    intermediate = tmp_path / "intermediate"
    intermediate.mkdir()
    latest = tmp_path / "latest"
    latest.mkdir()
    (latest / "route.php").write_text("<?php\nfunction endpoint() {}\n", encoding="utf-8")
    scanned_roots, rendered_roots = [], []
    real_scan = GraftAgent.scan
    real_render = window.on_scan_finished

    def scan(agent):
        scanned_roots.append(agent.root_dir)
        if agent is old_agent:
            old_started.set()
            assert old_release.wait(5)
            if old_scan_fails:
                raise RuntimeError("Old project is no longer available")
        elif agent.root_dir == latest:
            new_started.set()
            assert new_release.wait(5)
        real_scan(agent)

    def render(stats, welcome=False):
        assert QThread.currentThread() == app.thread()
        rendered_roots.append(window.agent.root_dir)
        real_render(stats, welcome=welcome)

    with patch.object(GraftAgent, "scan", autospec=True, side_effect=scan), \
         patch.object(window, "on_scan_finished", side_effect=render), \
         patch("desktop.main_window.QMessageBox.warning") as warning:
        try:
            window.do_scan()
            assert old_started.wait(1)
            window.sidebar.project_switched.emit(str(intermediate))
            window.sidebar.project_switched.emit(str(latest))
            assert window.sidebar.tree.topLevelItemCount() == 0
            assert window.prompt.target_file_combo.count() == 1

            old_release.set()
            wait_until(app, new_started.is_set)
            assert rendered_roots == []
            warning.assert_not_called()

            new_release.set()
            wait_until(app, lambda: window.sidebar.tree.topLevelItemCount() == 1)
            assert rendered_roots == [latest]
            assert scanned_roots == [old_agent.root_dir, latest]
            item = window.sidebar.tree.topLevelItem(0)
            assert item.text(0) == "route.php"
            assert not item.isHidden()
            assert window.sidebar.lbl_stats.text() == "1 tệp · 1 symbols"
            assert window.prompt.target_file_combo.itemData(1) == "route.php"
            window.sidebar.tree.itemClicked.emit(item, 0)
            assert window.editor.current_file == "route.php"
            assert "function endpoint" in window.editor.code_editor.toPlainText()
            warning.assert_not_called()
        finally:
            old_release.set()
            new_release.set()
            for _ in range(3):
                worker = getattr(window, "scan_worker", None)
                if worker is not None:
                    worker.wait(2000)
                app.processEvents()
