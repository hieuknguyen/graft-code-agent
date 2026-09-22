import os
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication
import pytest

from config import AppConfig, save_config, load_config
from core.context_builder import GRAFT_SYSTEM_INSTRUCTION
from desktop.main_window import MainWindow
from desktop.dialogs.settings_dialog import SettingsDialog
from core.session_manager import SessionManager


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setStyle("Fusion")
    return instance


def test_command_queue_policy_in_instruction():
    """The prompt permits continued work while respecting runtime and approval limits."""
    assert "no prompt-imposed command" in GRAFT_SYSTEM_INSTRUCTION
    assert "Command Queue" in GRAFT_SYSTEM_INSTRUCTION


def test_config_max_feedback_loops_default_and_persistence(tmp_path):
    """Kiểm tra cấu hình max_feedback_loops mặc định là 0 và lưu trữ yaml thành công."""
    cfg = AppConfig()
    assert cfg.max_feedback_loops == 0

    cfg.max_feedback_loops = 10
    config_file = tmp_path / "config.yaml"
    with patch("config.CONFIG_FILE", config_file):
        save_config(cfg)
        loaded = load_config()
        assert loaded.max_feedback_loops == 10

        # Đặt lại 0 = không giới hạn
        loaded.max_feedback_loops = 0
        save_config(loaded)
        reloaded = load_config()
        assert reloaded.max_feedback_loops == 0


def test_settings_dialog_max_feedback_loops(app):
    """Kiểm tra SettingsDialog hiển thị và lưu spinbox max_feedback_loops."""
    cfg = AppConfig(max_feedback_loops=0)
    dlg = SettingsDialog(cfg)
    assert dlg.spin_max_loops.value() == 0

    dlg.spin_max_loops.setValue(15)
    with patch("desktop.dialogs.settings_dialog.save_config"), \
         patch("desktop.dialogs.settings_dialog.QMessageBox.information"):
        dlg.save_settings()
        assert cfg.max_feedback_loops == 15


def test_main_window_unlimited_loops_and_command_queue(app, tmp_path):
    """Kiểm tra MainWindow không giới hạn bước lặp khi max_feedback_loops == 0 và hỗ trợ hàng đợi đa lệnh."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('test')\n", encoding="utf-8")

    cfg = AppConfig(max_feedback_loops=0)

    with patch("desktop.main_window.SessionManager", return_value=SessionManager(str(tmp_path / "history"))), \
         patch("desktop.main_window.load_config", return_value=cfg), \
         patch.object(MainWindow, "initial_setup"):
        window = MainWindow(str(project))
        assert window.max_feedback_loops == 0
        assert window.command_queue == []

        # 1. Kiểm tra hàng đợi đa lệnh (Multi-command queuing)
        fake_commands = [
            {"command": "pip install pytest", "description": "Lệnh 1"},
            {"command": "pytest tests/ -v", "description": "Lệnh 2"},
            {"command": "python main.py", "description": "Lệnh 3"}
        ]
        res = {
            "success": True,
            "response": "Tôi sẽ chạy 3 lệnh liên tiếp.",
            "commands": fake_commands,
            "actions": [],
            "create_files": [],
            "delete_files": [],
        }

        window.current_task = "chạy 3 lệnh"
        with patch.object(window, "run_terminal_command") as mock_run:
            window.on_graft_finished(res)
            # Lệnh đầu tiên phải được kích hoạt, 2 lệnh còn lại lưu vào hàng đợi
            assert len(window.command_queue) == 2
            assert window.command_queue[0] == "pytest tests/ -v"
            assert window.command_queue[1] == "python main.py"

        # 2. Giả lập lệnh 1 kết thúc -> Tự động bật lệnh 2 trong hàng đợi
        with patch.object(window, "run_terminal_command") as mock_run:
            window.feedback_loop_active = True
            window.prompt.chk_feedback.setChecked(True)
            window.on_command_completed("pip install pytest", exit_code=0, full_log="Successfully installed")
            assert len(window.command_queue) == 1
            assert window.command_queue[0] == "python main.py"

        # 3. Giả lập lệnh 2 kết thúc -> Tự động bật lệnh 3 trong hàng đợi
        with patch.object(window, "run_terminal_command") as mock_run:
            window.on_command_completed("pytest tests/ -v", exit_code=0, full_log="1 passed")
            assert len(window.command_queue) == 0

        # 4. Khi hàng đợi rỗng và max_feedback_loops == 0:
        # feedback_loop_count có thể vượt quá 6 mà không bị ngắt!
        window.feedback_loop_count = 10  # Đã chạy 10 bước
        with patch("desktop.main_window.AgentFeedbackWorker"):
            window.start_agent_feedback_step("python main.py", exit_code=0, full_log="App output")
            assert window.feedback_loop_count == 11
            assert window.feedback_loop_active is True

        # 5. Dừng tiến trình chủ động -> xóa sạch hàng đợi và ngắt loop
        window.command_queue = ["dummy1", "dummy2"]
        window.on_stop_process_requested()
        assert window.command_queue == []
        assert window.feedback_loop_active is False

        window.close()
        window.deleteLater()
