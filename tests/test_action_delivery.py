"""Recover tutorial-only answers to action requests without executing examples."""

import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from config import AppConfig
from core.agent import GraftAgent
from core.session_manager import SessionManager
from core.task_intent import is_action_request
from desktop.main_window import MainWindow


CHART_REQUEST = "giúp tôi vẽ 1 đồ thị giá bitcoin trong tuần"
TUTORIAL = """Để vẽ đồ thị, bạn có thể chọn HTML hoặc Python.
Tạo tệp `chart.py` rồi chạy:
```python
import matplotlib.pyplot as plt
plt.show()
```
```bash
python chart.py
```
Hãy cho biết định dạng bạn muốn để tôi hỗ trợ triển khai cụ thể!
"""
CHART_ACTIONS = """Tôi đã chuẩn bị tệp và lệnh hiển thị biểu đồ.
<<<CREATE_FILE
File: chart.py
```python
# Synthetic chart fixture; no market data is used in this test.
import matplotlib.pyplot as plt
plt.plot([1, 2], [10, 20])
plt.show()
```
<<<END_CREATE_FILE
<<<RUN_COMMAND
Command: python chart.py
Description: Display the chart.
<<<END_RUN_COMMAND
"""
READ_CHART = "<<<READ_FILE\nFile: chart.py\n<<<END_READ_FILE"
CHART_EDIT = """<<<GRAFT_ACTION
Action: REPLACE
File: chart.py
Symbol: draw
```python
def draw():
    return 'updated'
```
>>>
"""


def reply(text, tokens=10):
    return {"success": True, "response": text, "tokens": {"total_tokens": tokens}}


@pytest.fixture
def agent(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    instance = GraftAgent(AppConfig(web_search=False), str(project))
    with patch("core.environment_inspector.EnvironmentInspector.inspect_project", return_value={"error": "Test environment"}):
        yield instance


@pytest.mark.parametrize("task", [
    CHART_REQUEST,
    "hãy sửa lỗi đăng nhập",
    "Tôi muốn tạo một biểu đồ",
    "Bạn có thể chạy bộ kiểm thử giúp tôi",
    "giup toi ve do thi",
    "Please help me plot the weekly prices",
    "Can you create a chart in this project?",
    "Fix the login failure",
])
def test_direct_work_requests_require_action_delivery(task):
    assert is_action_request(task)


@pytest.mark.parametrize("task", [
    "Giải thích cách vẽ đồ thị bằng Python",
    "Hướng dẫn tôi tạo biểu đồ",
    "Chỉ cần giải thích, không tạo file",
    "Vẽ biểu đồ như thế nào? Chỉ hướng dẫn thôi",
    "How do I plot a chart?",
    "Explain why the script fails",
    "Create an example but do not modify files",
    "Only explain how to run chart.py",
])
def test_explanation_requests_are_not_forced_into_actions(task):
    assert not is_action_request(task)


def test_chart_tutorial_is_corrected_into_explicit_actions(agent):
    images = ["data:image/png;base64,test-fixture"]
    with patch.object(agent.client, "query_ai", side_effect=[reply(TUTORIAL), reply(CHART_ACTIONS, 20)]) as query:
        result = agent.plan_and_graft(CHART_REQUEST, images=images)
    assert query.call_count == 2
    assert "REQUESTED DELIVERY: ACTIONABLE WORK" in query.call_args_list[0].args[0]
    assert "ACTION DELIVERY CORRECTION" in query.call_args_list[1].args[0]
    assert CHART_REQUEST in query.call_args_list[1].args[0]
    assert TUTORIAL in query.call_args_list[1].args[0]
    assert all(call.kwargs["images"] == images for call in query.call_args_list)
    assert result["create_files"][0]["file"] == "chart.py"
    assert result["commands"][0]["command"] == "python chart.py"
    assert result["tokens"]["total_tokens"] == 30
    assert result["action_warning"] == ""
    assert not (agent.root_dir / "chart.py").exists()  # Planning never applies the proposal.


def test_valid_actions_do_not_trigger_an_extra_request(agent):
    with patch.object(agent.client, "query_ai", return_value=reply(CHART_ACTIONS)) as query:
        result = agent.plan_and_graft(CHART_REQUEST)
    assert query.call_count == 1
    assert len(result["commands"]) == 1


@pytest.mark.parametrize("task", ["Giải thích cách vẽ đồ thị", "Only explain, do not create files"])
def test_explanations_keep_markdown_examples_without_retry_or_execution(agent, task):
    with patch.object(agent.client, "query_ai", return_value=reply(TUTORIAL)) as query:
        result = agent.plan_and_graft(task)
    assert query.call_count == 1
    assert result["commands"] == []
    assert result["create_files"] == []
    assert result["action_warning"] == ""
    assert "python chart.py" in result["response"]


def test_persistent_prose_stops_after_one_correction_with_visible_warning(agent):
    with patch.object(agent.client, "query_ai", return_value=reply(TUTORIAL)) as query:
        result = agent.plan_and_graft(CHART_REQUEST)
    assert query.call_count == 2
    assert result["commands"] == []
    assert result["create_files"] == []
    assert result["action_warning"]
    assert not (agent.root_dir / "chart.py").exists()


def test_failed_correction_keeps_the_draft_without_claiming_execution(agent):
    with patch.object(agent.client, "query_ai", side_effect=[
        reply(TUTORIAL), {"success": False, "error": "Gateway unavailable"},
    ]) as query:
        result = agent.plan_and_graft(CHART_REQUEST)
    assert query.call_count == 2
    assert "Gateway unavailable" not in result["response"]
    assert "python chart.py" in result["response"]
    assert result["action_warning"]
    assert result["commands"] == []


@pytest.mark.parametrize("replies", [
    [reply(TUTORIAL), reply(READ_CHART), reply(CHART_EDIT)],
    [reply(READ_CHART), reply(TUTORIAL), reply(CHART_EDIT)],
])
def test_correction_and_retrieval_can_happen_in_either_order(agent, replies):
    (agent.root_dir / "chart.py").write_text("def draw():\n    return 'original'\n", encoding="utf-8")
    agent.scan()
    with patch.object(agent.client, "query_ai", side_effect=replies) as query:
        result = agent.plan_and_graft("Sửa hàm draw trong chart.py")
    assert query.call_count == 3
    assert "return 'original'" in query.call_args_list[-1].args[0]
    assert "REQUESTED FILE CONTENTS" in query.call_args_list[-1].args[0]
    assert result["actions"][0]["success"] is True
    assert "return 'updated'" in result["actions"][0]["new_code"]
    assert result["tokens"]["total_tokens"] == 30
    assert result["action_warning"] == ""


def test_repeated_read_after_retrieval_limit_does_not_loop(agent):
    with patch.object(agent.client, "query_ai", return_value=reply(READ_CHART)) as query:
        result = agent.plan_and_graft("Sửa file chart.py")
    assert query.call_count == 2
    assert "was not found" in query.call_args_list[-1].args[0]
    assert result["commands"] == []
    assert result["action_warning"]


@pytest.fixture
def window(agent, tmp_path):
    app = QApplication.instance() or QApplication([])
    agent.config.auto_apply = True
    with patch("desktop.main_window.SessionManager", return_value=SessionManager(str(tmp_path / "history"))), \
         patch("desktop.main_window.load_config", return_value=agent.config), \
         patch.object(MainWindow, "initial_setup"):
        widget = MainWindow(str(agent.root_dir))
        widget.agent = agent
        widget.current_task = CHART_REQUEST
        widget.feedback_loop_active = True
        yield widget
        widget.on_stop_process_requested()
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_recovered_actions_reach_auto_apply_and_launch_queue(window):
    with patch.object(window.agent.client, "query_ai", side_effect=[reply(TUTORIAL), reply(CHART_ACTIONS)]):
        result = window.agent.plan_and_graft(CHART_REQUEST)
    with patch.object(window, "_schedule_automatic_command") as schedule:
        window.on_graft_finished(result)
    assert "plt.show()" in (Path(window.root_dir) / "chart.py").read_text(encoding="utf-8")
    schedule.assert_called_once_with("python chart.py", 600)


def test_ui_reports_missing_actions_instead_of_auto_applied_success(window):
    with patch.object(window.agent.client, "query_ai", return_value=reply(TUTORIAL)):
        result = window.agent.plan_and_graft(CHART_REQUEST)
    with patch.object(window, "_schedule_automatic_command") as schedule:
        window.on_graft_finished(result)
    schedule.assert_not_called()
    messages = window.editor.chat_view.raw_messages
    ai_message = next(message for message in messages if message["role"] == "ai")
    assert ai_message["auto_applied"] is False
    assert any(message.get("title") == "CHƯA CÓ HÀNH ĐỘNG THỰC THI" for message in messages)
    assert window.feedback_loop_active is False
