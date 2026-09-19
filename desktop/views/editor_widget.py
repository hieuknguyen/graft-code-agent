import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QPlainTextEdit,
    QTextBrowser, QLabel, QHBoxLayout
)
from PySide6.QtGui import QFont, QTextCursor
from desktop.theme import format_diff_html
from desktop.views.chat_widget import ChatWidget
from desktop.views.terminal_widget import TerminalWidget

class EditorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.tabs = QTabWidget()

        # Tab 0: Trò Chuyện & AI Agent
        self.chat_view = ChatWidget(self)
        self.tabs.addTab(self.chat_view, "💬 Trợ Lý AI (Chat)")

        # Tab 1: Code Viewer
        self.code_viewer_tab = QWidget()
        code_layout = QVBoxLayout(self.code_viewer_tab)
        code_layout.setContentsMargins(4, 4, 4, 4)

        self.code_header = QLabel("Chưa chọn tệp mã nguồn nào")
        self.code_header.setStyleSheet("color: #818cf8; font-weight: bold; padding: 4px 8px;")
        code_layout.addWidget(self.code_header)

        self.code_editor = QPlainTextEdit()
        self.code_editor.setFont(QFont("Consolas", 10))
        self.code_editor.setReadOnly(True)
        code_layout.addWidget(self.code_editor)

        self.tabs.addTab(self.code_viewer_tab, "📄 Mã Nguồn (Code)")

        # Tab 2: Diff Viewer
        self.diff_viewer_tab = QWidget()
        diff_layout = QVBoxLayout(self.diff_viewer_tab)
        diff_layout.setContentsMargins(4, 4, 4, 4)

        self.diff_header = QLabel("Bảng So Sánh Cấy Ghép Mã Nguồn (Unified Diff)")
        self.diff_header.setStyleSheet("color: #38bdf8; font-weight: bold; padding: 4px 8px;")
        diff_layout.addWidget(self.diff_header)

        self.diff_browser = QTextBrowser()
        self.diff_browser.setFont(QFont("Consolas", 10))
        self.diff_browser.setOpenExternalLinks(False)
        self.set_diff("")
        diff_layout.addWidget(self.diff_browser)

        self.tabs.addTab(self.diff_viewer_tab, "🔍 So Sánh Cấy Ghép (Diff)")

        # Tab 3: Terminal & Tiến Trình
        self.terminal_view = TerminalWidget(self)
        self.tabs.addTab(self.terminal_view, "💻 Terminal & Tiến Trình")

        layout.addWidget(self.tabs)

    def set_file_content(self, path: str, content: str, line_number: int = None):
        self.current_file = path
        self.code_header.setText(f"📄 {path}")
        self.code_editor.setPlainText(content)
        self.tabs.setCurrentIndex(1)

        if line_number is not None and line_number > 0:
            cursor = self.code_editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            for _ in range(line_number - 1):
                cursor.movePosition(QTextCursor.MoveOperation.Down)
            self.code_editor.setTextCursor(cursor)
            self.code_editor.centerCursor()

    def set_diff(self, diff_text: str):
        html = format_diff_html(diff_text)
        self.diff_browser.setHtml(html)
        if diff_text and diff_text.strip():
            self.tabs.setCurrentIndex(2)
