import os
import pytest
from unittest.mock import patch
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication, QMessageBox

from config import AppConfig
from core.session_manager import SessionManager
from desktop.main_window import MainWindow
from desktop.views.chat_widget import ChatWidget

@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setStyle("Fusion")
    return instance

@pytest.fixture
def test_env(tmp_path):
    storage = tmp_path / "storage"
    mgr = SessionManager(str(storage))
    p1_dir = tmp_path / "proj1"
    p1_dir.mkdir()
    p2_dir = tmp_path / "proj2"
    p2_dir.mkdir()
    p1 = mgr.get_or_create_project(str(p1_dir))
    p2 = mgr.get_or_create_project(str(p2_dir))
    return mgr, p1, p2, p1_dir, p2_dir

def test_session_manager_message_deletion(test_env):
    mgr, p1, _, _, _ = test_env
    conv = mgr.create_conversation(p1["id"], "Test Chat")
    mgr.append_message(p1["id"], conv["id"], {"role": "user", "text": "Message 1"})
    mgr.append_message(p1["id"], conv["id"], {"role": "ai", "text": "Message 2"})
    mgr.append_message(p1["id"], conv["id"], {"role": "user", "text": "Message 3"})

    saved = mgr.get_conversation(p1["id"], conv["id"])
    assert len(saved["messages"]) == 3

    # Delete middle message (index 1)
    succ = mgr.delete_message(p1["id"], conv["id"], 1)
    assert succ is True
    updated = mgr.get_conversation(p1["id"], conv["id"])
    assert len(updated["messages"]) == 2
    assert updated["messages"][0]["text"] == "Message 1"
    assert updated["messages"][1]["text"] == "Message 3"

    # Clear all messages
    succ = mgr.clear_conversation_messages(p1["id"], conv["id"])
    assert succ is True
    cleared = mgr.get_conversation(p1["id"], conv["id"])
    assert len(cleared["messages"]) == 0

def test_chat_widget_message_deletion(app):
    chat = ChatWidget()
    chat.add_user_message("Hello world")
    chat.add_ai_message("Hi there!")
    assert len(chat.raw_messages) == 2

    # Simulate clicking delete on first message with confirmation Yes
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        chat.on_link_clicked(QUrl("deletemsg:///0"))

    assert len(chat.raw_messages) == 1
    assert chat.raw_messages[0]["text"] == "Hi there!"

def test_main_window_delete_conversation_and_project(app, tmp_path):
    storage_dir = tmp_path / "history"
    mgr = SessionManager(str(storage_dir))
    proj1 = tmp_path / "proj1"
    proj1.mkdir()
    (proj1 / "test.py").write_text("# test", encoding="utf-8")
    proj2 = tmp_path / "proj2"
    proj2.mkdir()

    mgr.get_or_create_project(str(proj1))
    mgr.get_or_create_project(str(proj2))

    with patch("desktop.main_window.SessionManager", return_value=mgr), \
         patch("desktop.main_window.load_config", return_value=AppConfig()), \
         patch.object(MainWindow, "initial_setup"):
        win = MainWindow(str(proj1))
        win.show()
        app.processEvents()

        # Create two conversations
        conv1 = mgr.create_conversation(win.current_project["id"], "Conv 1")
        conv2 = mgr.create_conversation(win.current_project["id"], "Conv 2")
        mgr.append_message(win.current_project["id"], conv1["id"], {"role": "user", "text": "Hello"})
        win.on_conversation_selected(conv1["id"])
        app.processEvents()

        assert win.current_conv_id == conv1["id"]

        # Delete current conversation with confirmation
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            win.confirm_delete_current_conversation()
            app.processEvents()

        # Should have switched to conv2 or created a new one
        convs = mgr.get_conversations(win.current_project["id"])
        conv_ids = [c["id"] for c in convs]
        assert conv1["id"] not in conv_ids

        # Delete non-active project (proj2)
        p2_record = next(p for p in mgr.get_projects() if os.path.abspath(p["path"]) == os.path.abspath(str(proj2)))
        win.on_delete_project_requested(p2_record["id"])
        app.processEvents()

        remaining_projects = mgr.get_projects()
        assert len(remaining_projects) == 1
        assert os.path.abspath(win.root_dir) == os.path.abspath(str(proj1))

        # Delete active project (proj1) -> should fallback
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
             patch.object(win, "do_scan"):
            win.confirm_delete_current_project()
            app.processEvents()

        assert not any(p["id"] == win.current_project["id"] and p["path"] == str(proj1) for p in mgr.get_projects())

        win.close()
        win.deleteLater()
        app.processEvents()

def test_prompt_enter_and_shift_enter_behavior(app):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest, QSignalSpy
    from desktop.views.prompt_widget import PromptWidget

    prompt = PromptWidget()
    prompt.show()
    app.processEvents()

    spy = QSignalSpy(prompt.graft_requested)

    from PySide6.QtGui import QTextCursor

    # Type first line
    prompt.prompt_edit.setPlainText("First line")
    prompt.prompt_edit.moveCursor(QTextCursor.MoveOperation.End)

    # Shift + Enter should insert a newline, NOT submit
    QTest.keyClick(prompt.prompt_edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert prompt.prompt_edit.toPlainText() == "First line\n"

    assert spy.count() == 0

    # Add second line
    prompt.prompt_edit.insertPlainText("Second line")
    assert prompt.prompt_edit.toPlainText() == "First line\nSecond line"

    # Enter (without Shift) should submit the prompt to AI
    QTest.keyClick(prompt.prompt_edit, Qt.Key.Key_Return)
    assert spy.count() == 1
    task, target, options = spy.at(0)
    assert task == "First line\nSecond line"
    assert prompt.prompt_edit.toPlainText() == ""

    prompt.close()
    prompt.deleteLater()
    app.processEvents()

