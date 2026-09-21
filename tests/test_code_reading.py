from pathlib import Path
from unittest.mock import MagicMock, patch
from config import AppConfig
from core.context_builder import build_graft_prompt, get_system_instruction, GRAFT_SYSTEM_INSTRUCTION
from core.agent import GraftAgent
from graft.graph import CodebaseGraph


def test_read_before_editing_in_system_instructions():
    """The English instructions retain the read-before-editing requirement."""
    assert "NEVER ASSUME CODE BY FILENAME" in GRAFT_SYSTEM_INSTRUCTION
    assert "<<<READ_FILE" in GRAFT_SYSTEM_INSTRUCTION
    instruction = get_system_instruction()
    assert "NEVER ASSUME CODE BY FILENAME" in instruction


def test_small_project_auto_codebase_injection(tmp_path):
    """Kiểm tra dự án nhỏ (<= 8 file, <= 1800 dòng) được tự động inject toàn bộ source code vào prompt."""
    file1 = tmp_path / "plot_btc.py"
    content1 = "import matplotlib.pyplot as plt\nprint('BTC chart')\n"
    file1.write_text(content1, encoding="utf-8")

    file2 = tmp_path / "utils.py"
    content2 = "def helper():\n    return 42\n"
    file2.write_text(content2, encoding="utf-8")

    graph = CodebaseGraph(str(tmp_path))
    graph.scan()

    prompt = build_graft_prompt("Vẽ đồ thị BTC", graph=graph, project_dir=str(tmp_path))
    
    assert "FULL INDEXED CODEBASE SOURCE" in prompt
    assert "plot_btc.py" in prompt
    assert "import matplotlib.pyplot as plt" in prompt
    assert "utils.py" in prompt
    assert "def helper():" in prompt


def test_large_project_smart_relevant_files_injection(tmp_path):
    """Kiểm tra dự án nhiều files (> 8 files) sử dụng cơ chế chấm điểm từ khóa và stem để nạp file liên quan."""
    # Tạo 10 files để vượt ngưỡng 8 files
    for i in range(10):
        f = tmp_path / f"module_{i}.py"
        f.write_text(f"# module {i} content\ndef func_{i}(): pass\n", encoding="utf-8")

    special = tmp_path / "btc_visualizer.py"
    special.write_text("import matplotlib.pyplot as plt\n# Visualize bitcoin\n", encoding="utf-8")

    graph = CodebaseGraph(str(tmp_path))
    graph.scan()

    prompt = build_graft_prompt("Hãy kiểm tra btc visualizer xem có lỗi gì", graph=graph, project_dir=str(tmp_path))
    
    assert "RELEVANT SOURCE FILES" in prompt
    assert "btc_visualizer.py" in prompt
    assert "matplotlib.pyplot" in prompt


def test_parse_all_actions_read_files(tmp_path):
    """Kiểm tra hàm parse_all_actions trích xuất chuẩn xác thẻ READ_FILE và clean_ai_response dọn sạch thẻ."""
    cfg = AppConfig()
    agent = GraftAgent(cfg, str(tmp_path))

    sample_ai = """Tôi thấy bạn cần vẽ đồ thị.
<<<READ_FILE
File: src/chart.py
<<<END_READ_FILE
Và một file khác:
[READ_FILE: config/settings.json]
Tôi sẽ kiểm tra nội dung 2 file này.
"""
    actions = agent.parse_all_actions(sample_ai)
    assert "src/chart.py" in actions["read_files"]
    assert "config/settings.json" in actions["read_files"]

    cleaned = agent.clean_ai_response(sample_ai)
    assert "<<<READ_FILE" not in cleaned
    assert "src/chart.py" not in cleaned or "Tôi thấy bạn" in cleaned
    assert "[READ_FILE" not in cleaned


def test_plan_and_graft_two_turn_file_reading(tmp_path):
    """Kiểm tra vòng lặp 2 lượt khi AI yêu cầu đọc file: lượt 2 nhận mã nguồn và cấy ghép thành công."""
    script_file = tmp_path / "plot_btc.py"
    script_file.write_text("print('Chỉ in text chứ không có GUI')\n", encoding="utf-8")

    cfg = AppConfig()
    agent = GraftAgent(cfg, str(tmp_path))
    agent.scan()

    # Turn 1: AI yêu cầu đọc file plot_btc.py
    turn1_response = """Để đảm bảo không đoán mò code, tôi cần đọc mã nguồn file plot_btc.py.
<<<READ_FILE
File: plot_btc.py
<<<END_READ_FILE
"""
    # Turn 2: AI nhận code, phát hiện không có GUI và tạo bản cấy ghép sửa
    turn2_response = """Tôi đã đọc kỹ plot_btc.py và thấy file chỉ in text. Tôi sẽ bổ sung giao diện đồ thị Matplotlib:
<<<GRAFT_ACTION
File: plot_btc.py
Symbol: all
Action: REPLACE
```python
import matplotlib.pyplot as plt
plt.plot([1, 2, 3], [60000, 62000, 65000])
plt.title("BTC Price")
plt.show()
```
>>>
"""
    with patch.object(agent.client, "query_ai", side_effect=[
        {"success": True, "response": turn1_response},
        {"success": True, "response": turn2_response}
    ]) as mock_ai:
        res = agent.plan_and_graft("Hãy hiển thị đồ thị BTC", target_file=None)

        # Đảm bảo client được gọi 2 lần (2-turn execution loop)
        assert mock_ai.call_count == 2
        # Lần gọi thứ 2 phải chứa nội dung thực tế của file plot_btc.py
        turn2_call_args = mock_ai.call_args_list[1]
        turn2_prompt = turn2_call_args[0][0]
        assert "Chỉ in text chứ không có GUI" in turn2_prompt
        assert "REQUESTED FILE CONTENTS" in turn2_prompt
        assert len(res["actions"]) == 1
        assert res["actions"][0]["file"] == "plot_btc.py"


def test_analyze_log_and_plan_next_injects_script_source(tmp_path):
    """Kiểm tra analyze_log_and_plan_next tự động nạp mã nguồn của kịch bản vừa chạy vào ngữ cảnh phân tích."""
    script_file = tmp_path / "run_analysis.py"
    script_content = "# Analysis script\nimport pandas as pd\ndf = pd.DataFrame({'a': [1]})\nprint('Done without GUI')\n"
    script_file.write_text(script_content, encoding="utf-8")

    cfg = AppConfig()
    agent = GraftAgent(cfg, str(tmp_path))

    with patch.object(agent.client, "query_ai", return_value={
        "success": True,
        "response": "Script chạy xong nhưng chưa có giao diện hiển thị. Tôi sẽ bổ sung GUI."
    }) as mock_ai:
        agent.analyze_log_and_plan_next(
            log_text="Process finished with exit code 0",
            exit_code=0,
            last_cmd=f"python {script_file.name}",
            goal="Hiển thị đồ thị trực quan cho tôi xem"
        )

        call_args = mock_ai.call_args[0][0]
        assert "SOURCE OF THE EXECUTED SCRIPT" in call_args
        assert "run_analysis.py" in call_args
        assert "Done without GUI" in call_args
