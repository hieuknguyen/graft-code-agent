import pytest
from core.text_utils import sanitize_latex
from desktop.views.chat_widget import ChatWidget
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    return instance


def test_sanitize_latex_temperature_and_degrees():
    # User's exact case from the app screenshot
    text = "$25^\\circ\\text{C}$ - 32^\\circ\\text{C}$ (Cảm giác thực tế có thể lên đến $35^\\circ\\text{C}$ vào buổi trưa)"
    sanitized = sanitize_latex(text)
    assert sanitized == "25°C - 32°C (Cảm giác thực tế có thể lên đến 35°C vào buổi trưa)"
    assert "$" not in sanitized
    assert "\\circ" not in sanitized
    assert "\\text" not in sanitized


def test_sanitize_latex_percentages_and_ranges():
    text = "Độ ẩm dao động từ $75\\% - 92\\%$"
    sanitized = sanitize_latex(text)
    assert sanitized == "Độ ẩm dao động từ 75% - 92%"
    assert "$" not in sanitized
    assert "\\" not in sanitized


def test_sanitize_latex_speed_and_time_units():
    text = "Gió cấp 2 - cấp 3 ($10 - 15\\text{ km/h}$). Mưa khoảng $15\\text{h}00 - 18\\text{h}30$."
    sanitized = sanitize_latex(text)
    assert sanitized == "Gió cấp 2 - cấp 3 (10 - 15 km/h). Mưa khoảng 15h00 - 18h30."
    assert "$" not in sanitized
    assert "\\text" not in sanitized


def test_sanitize_latex_preserves_currency():
    text = "Sản phẩm này có giá $50, còn sản phẩm kia từ $10 đến $20 một món."
    sanitized = sanitize_latex(text)
    assert "$50" in sanitized
    assert "$10" in sanitized
    assert "$20" in sanitized


def test_sanitize_latex_preserves_code_blocks():
    text = "Chạy lệnh sau trong terminal:\n```bash\necho $VAR\nprice=$25\n```\nhoặc dùng `$VAR` trong file."
    sanitized = sanitize_latex(text)
    assert "echo $VAR" in sanitized
    assert "price=$25" in sanitized
    assert "`$VAR`" in sanitized


def test_sanitize_latex_math_formulas():
    text = "Công thức: $E = mc^2$ và $\\frac{a}{b} \\approx 0.5$ với $\\sqrt{x} \\le 10$."
    sanitized = sanitize_latex(text)
    assert "E = mc²" in sanitized
    assert "a/b ≈ 0.5" in sanitized
    assert "√(x) ≤ 10" in sanitized
    assert "$" not in sanitized


def test_chat_widget_markdown_to_html_latex_sanitization(app):
    chat = ChatWidget()
    raw_ai_table = (
        "| Thông số | Chi tiết dự báo |\n"
        "|---|---|\n"
        "| Nhiệt độ | $25^\\circ\\text{C}$ - 32^\\circ\\text{C}$ |\n"
        "| Độ ẩm | $75% - 92%$ |\n"
        "| Gió | $10 - 15\\text{ km/h}$ |\n"
    )
    html_out = chat.markdown_to_html(raw_ai_table)
    assert "25°C - 32°C" in html_out
    assert "75% - 92%" in html_out
    assert "10 - 15 km/h" in html_out
    assert "$25" not in html_out
    assert "\\circ" not in html_out
    assert "\\text" not in html_out
