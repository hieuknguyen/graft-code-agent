import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from config import AppConfig
from core.agent import GraftAgent
from core.tool_runtime import ToolRuntime, ToolResult
from desktop.dialogs.settings_dialog import SettingsDialog
from desktop.main_window import MainWindow
from desktop.views.prompt_widget import PromptWidget


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setStyle("Fusion")
    return instance


def test_tool_runtime_web_search_ddg_html_mock(tmp_path):
    runtime = ToolRuntime(str(tmp_path))

    fake_ddg_html = """
    <html>
      <body>
        <div class="result">
          <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fweather&rut=1">Thời tiết hôm nay</a>
          <a class="result__snippet">Dự báo thời tiết hôm nay nhiệt độ 30 độ C.</a>
        </div>
      </body>
    </html>
    """

    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_ddg_html.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = runtime.web_search("thời tiết", max_results=5)
        assert res.ok is True
        data = res.data
        assert data["query"] == "thời tiết"
        assert len(data["results"]) == 1
        assert data["results"][0]["title"] == "Thời tiết hôm nay"
        assert data["results"][0]["url"] == "https://example.com/weather"
        assert "30 độ C" in data["results"][0]["snippet"]


def test_tool_runtime_web_search_bing_mock(tmp_path):
    runtime = ToolRuntime(str(tmp_path))

    fake_html = """
    <html>
      <body>
        <li class="b_algo">
          <h2><a href="https://example.com/python-docs">Python Official Docs</a></h2>
          <div class="b_caption"><p>Python is a programming language that lets you work quickly.</p></div>
        </li>
        <li class="b_algo">
          <h2><a href="https://example.com/fastapi">FastAPI Framework</a></h2>
          <p>FastAPI is a modern high-performance web framework for Python.</p>
        </li>
      </body>
    </html>
    """

    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_html.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = runtime.web_search("Python docs", max_results=5)
        assert res.ok is True
        data = res.data
        assert data["query"] == "Python docs"
        assert len(data["results"]) == 2
        assert data["results"][0]["title"] == "Python Official Docs"
        assert data["results"][0]["url"] == "https://example.com/python-docs"
        assert "programming language" in data["results"][0]["snippet"]


def test_tool_runtime_web_search_ddg_fallback(tmp_path):
    runtime = ToolRuntime(str(tmp_path))

    # Bing returns empty / fails, DuckDuckGo JSON succeeds
    mock_ddg_json = """{
        "Abstract": "Python is a high-level general-purpose programming language.",
        "AbstractURL": "https://en.wikipedia.org/wiki/Python_(programming_language)",
        "Heading": "Python (programming language)",
        "RelatedTopics": [
            {
                "Text": "Python Software Foundation - non-profit organization",
                "FirstURL": "https://duckduckgo.com/Python_Software_Foundation"
            }
        ]
    }"""

    mock_bing_empty = MagicMock()
    mock_bing_empty.read.return_value = b"<html><body>No results</body></html>"
    mock_bing_empty.__enter__.return_value = mock_bing_empty

    mock_ddg_resp = MagicMock()
    mock_ddg_resp.read.return_value = mock_ddg_json.encode("utf-8")
    mock_ddg_resp.__enter__.return_value = mock_ddg_resp

    def fake_urlopen(req, *args, **kwargs):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "bing.com" in url:
            return mock_bing_empty
        return mock_ddg_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        res = runtime.web_search("Python", max_results=5)
        assert res.ok is True
        data = res.data
        assert len(data["results"]) >= 1
        assert "Python" in data["results"][0]["title"]


def test_tool_runtime_dispatch_web_search(tmp_path):
    runtime = ToolRuntime(str(tmp_path))

    fake_result = ToolResult(
        ok=True,
        data={"query": "test query", "results": [{"title": "T", "snippet": "S", "url": "U"}]},
    )
    with patch.object(runtime, "web_search", return_value=fake_result) as mock_search:
        res = runtime.dispatch("web_search", {"query": "test query", "max_results": 3})
        assert res["ok"] is True
        mock_search.assert_called_once_with(query="test query", max_results=3)


def test_autonomous_web_search_evaluation(tmp_path):
    cfg = AppConfig(web_search=True)
    agent = GraftAgent(cfg, str(tmp_path))

    # 1. Local tasks must NOT trigger search
    local_tasks = [
        "Sửa hàm calculate_total trong utils.py",
        "Thêm nút bấm Gửi vào giao diện",
        "Xóa file temp.log",
        "Chạy lệnh pytest tests/ -v",
        "Tạo file config.json với nội dung rỗng",
    ]
    for task in local_tasks:
        decision = agent.evaluate_web_search_need(task)
        assert decision["need_search"] is False, f"Expected False for local task: {task}"

    # 2. External questions & errors MUST trigger search autonomously
    external_tasks = [
        "Thư viện nào tốt nhất để render Markdown trong PySide6?",
        "Lỗi TypeError: Cannot read properties of undefined (reading 'install') khi dùng vue-router v4 trong Vite",
        "Cách cấu hình CORS trong FastAPI",
        "Giải thích các breaking changes trong Tailwind CSS v4",
        "Tìm kiếm tài liệu thư viện httpx",
    ]
    for task in external_tasks:
        decision = agent.evaluate_web_search_need(task)
        assert decision["need_search"] is True, f"Expected True for external task: {task}"
        assert len(decision["query"]) > 0

    # 3. When disabled by user -> always False
    agent.config.web_search = False
    for task in external_tasks:
        decision = agent.evaluate_web_search_need(task)
        assert decision["need_search"] is False, f"Expected False when disabled for: {task}"


def test_agent_generate_web_search_context(tmp_path):
    cfg = AppConfig(web_search=True)
    agent = GraftAgent(cfg, str(tmp_path))

    fake_res = ToolResult(
        ok=True,
        data={
            "query": "cấu hình CORS trong FastAPI",
            "results": [
                {
                    "title": "CORS (Cross-Origin Resource Sharing) - FastAPI",
                    "snippet": "You can configure CORS using CORSMiddleware in FastAPI.",
                    "url": "https://fastapi.tiangolo.com/tutorial/cors/",
                }
            ],
        },
    )

    with patch.object(agent.runtime, "web_search", return_value=fake_res) as mock_search:
        ctx = agent.generate_web_search_context("Cách cấu hình CORS trong FastAPI")
        assert "LIVE WEB SEARCH RESULTS" in ctx
        assert "FastAPI" in ctx
        assert "https://fastapi.tiangolo.com/tutorial/cors/" in ctx
        mock_search.assert_called_once()

    # Local task produces empty context
    ctx_local = agent.generate_web_search_context("Sửa hàm format_date trong helper.py")
    assert ctx_local == ""


def test_in_flight_autonomous_web_search(tmp_path):
    cfg = AppConfig(web_search=True)
    agent = GraftAgent(cfg, str(tmp_path))

    # AI response in round 1 asks for <<<WEB_SEARCH
    ai_resp_1 = {
        "success": True,
        "response": (
            "Tôi cần tìm kiếm tài liệu mới về Pydantic v2.\n"
            "<<<WEB_SEARCH\nQuery: pydantic v2 migration guide\n<<<END_WEB_SEARCH\n"
        ),
        "tokens": {"input_tokens": 10, "output_tokens": 20},
    }

    ai_resp_2 = {
        "success": True,
        "response": "Dựa trên tài liệu Pydantic v2, bạn cần thay thế .dict() bằng .model_dump().",
        "tokens": {"input_tokens": 30, "output_tokens": 40},
    }

    fake_search_res = ToolResult(
        ok=True,
        data={
            "query": "pydantic v2 migration guide",
            "results": [
                {
                    "title": "Migration Guide - Pydantic",
                    "snippet": "Use model_dump instead of dict in V2.",
                    "url": "https://docs.pydantic.dev/latest/migration/",
                }
            ],
        },
    )

    with patch.object(agent.client, "query_ai", side_effect=[ai_resp_1, ai_resp_2]) as mock_ai, \
         patch.object(agent.runtime, "web_search", return_value=fake_search_res) as mock_search:
        res = agent.plan_and_graft("Giải thích thay đổi cần sửa trong file models.py để migrate sang pydantic v2")
        assert res["success"] is True
        assert "model_dump" in res["response"]
        assert "<<<WEB_SEARCH" not in res["response"]  # Tags are stripped from clean output
        assert mock_ai.call_count == 2
        mock_search.assert_called_once_with("pydantic v2 migration guide", max_results=5)


def test_prompt_widget_web_search_toggle(app):
    prompt = PromptWidget()
    assert hasattr(prompt, "chk_web")
    prompt.chk_web.setChecked(True)

    received_options = {}

    def on_graft(task, target_file, options):
        nonlocal received_options
        received_options = options

    prompt.graft_requested.connect(on_graft)
    prompt.prompt_edit.setPlainText("Test task for web search")
    prompt.submit_prompt()

    assert received_options.get("web_search") is True

    # Test unchecked
    prompt.chk_web.setChecked(False)
    prompt.prompt_edit.setPlainText("Second task")
    prompt.submit_prompt()
    assert received_options.get("web_search") is False


def test_settings_dialog_web_search(app):
    cfg = AppConfig(web_search=False)
    dialog = SettingsDialog(cfg)
    assert hasattr(dialog, "chk_web_search")
    assert dialog.chk_web_search.isChecked() is False

    dialog.chk_web_search.setChecked(True)
    with patch("desktop.dialogs.settings_dialog.save_config") as mock_save:
        with patch("desktop.dialogs.settings_dialog.QMessageBox.information"):
            dialog.save_settings()
            assert cfg.web_search is True
            mock_save.assert_called_once()


def test_main_window_web_search_sync(app, tmp_path):
    cfg = AppConfig(web_search=True)
    with patch("desktop.main_window.load_config", return_value=cfg), \
         patch("desktop.main_window.SessionManager"):
        win = MainWindow(str(tmp_path))
        try:
            assert win.prompt.chk_web.isChecked() is True

            # Simulate submit from prompt widget
            win.prompt.chk_web.setChecked(False)
            with patch("desktop.main_window.GraftWorker"):
                win.on_graft_requested("Test", "", {"web_search": False, "thinking": True})
                assert win.config.web_search is False
        finally:
            win.close()
