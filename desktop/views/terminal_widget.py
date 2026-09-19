from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextBrowser
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QTextCursor

class TerminalWidget(QWidget):
    run_requested = Signal(str)
    stdin_requested = Signal(str)
    kill_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_running = False
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        header = QHBoxLayout()
        icon = QLabel("💻")
        icon.setStyleSheet("font-size: 15px;")
        header.addWidget(icon)

        title = QLabel("TERMINAL & TIẾN TRÌNH HỆ THỐNG")
        title.setStyleSheet("font-weight: bold; color: #38bdf8; font-size: 12px;")
        header.addWidget(title)
        header.addStretch()

        self.btn_clear = QPushButton("🗑️ Xóa Log")
        self.btn_clear.clicked.connect(self.clear_output)
        header.addWidget(self.btn_clear)

        self.btn_kill = QPushButton("⏹ Dừng Lệnh")
        self.btn_kill.setStyleSheet("color: #f87171; border-color: #7f1d1d;")
        self.btn_kill.setEnabled(False)
        self.btn_kill.clicked.connect(self.kill_requested.emit)
        header.addWidget(self.btn_kill)

        layout.addLayout(header)

        self.output_browser = QTextBrowser()
        self.output_browser.setFont(QFont("Consolas", 10))
        self.output_browser.setStyleSheet("""
            QTextBrowser {
                background-color: #050811;
                color: #e2e8f0;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        layout.addWidget(self.output_browser)

        input_box = QHBoxLayout()
        lbl_prompt = QLabel("$")
        lbl_prompt.setStyleSheet("font-family: Consolas; font-weight: bold; color: #34d399; font-size: 14px;")
        input_box.addWidget(lbl_prompt)

        self.cmd_input = QLineEdit()
        self.cmd_input.setFont(QFont("Consolas", 10))
        self.cmd_input.setPlaceholderText("Nhập lệnh terminal (ví dụ: php artisan route:list, npm test, python ...) và nhấn Enter...")
        self.cmd_input.returnPressed.connect(self.on_submit)
        input_box.addWidget(self.cmd_input)

        self.btn_run = QPushButton("▶️ Chạy")
        self.btn_run.setObjectName("primaryButton")
        self.btn_run.clicked.connect(self.on_submit)
        input_box.addWidget(self.btn_run)

        layout.addLayout(input_box)

    def on_submit(self):
        cmd = self.cmd_input.text().strip()
        if not cmd:
            return
        if self.is_running:
            self.stdin_requested.emit(cmd)
            self.cmd_input.clear()
        else:
            self.run_requested.emit(cmd)
            self.cmd_input.clear()

    def append_output(self, text: str, is_error: bool = False):
        color = "#f87171" if is_error else "#e2e8f0"
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        self.output_browser.moveCursor(QTextCursor.MoveOperation.End)
        self.output_browser.insertHtml(f"<span style='color: {color}; font-family: Consolas, monospace;'>{escaped}</span>")
        self.output_browser.moveCursor(QTextCursor.MoveOperation.End)

    def clear_output(self):
        self.output_browser.clear()

    def set_running(self, running: bool):
        self.is_running = running
        self.btn_kill.setEnabled(running)
        if running:
            self.btn_run.setText("↵ Gửi Input")
            self.btn_run.setEnabled(True)
            self.cmd_input.setPlaceholderText("Tiến trình đang chạy... Nhập dữ liệu (y/n, input) rồi Enter hoặc nhấn [Gửi Input]...")
        else:
            self.btn_run.setText("▶️ Chạy")
            self.btn_run.setEnabled(True)
            self.cmd_input.setPlaceholderText("Nhập lệnh terminal (ví dụ: php artisan serve, npm test, python ...) và nhấn Enter...")

