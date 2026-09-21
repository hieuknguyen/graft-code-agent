import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTextBrowser,
    QLabel, QPushButton, QSplitter, QStackedWidget, QFrame, QSizePolicy, QMenu
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor

from desktop.icons import icon
from desktop.theme import format_diff_html
from desktop.views.code_view import CodeView
from desktop.views.chat_widget import ChatWidget
from desktop.views.terminal_widget import TerminalWidget


class EditorWidget(QWidget):
    open_folder_requested = Signal()
    search_requested = Signal()
    focus_agent_requested = Signal()
    new_conversation_requested = Signal()
    history_requested = Signal()
    sidebar_toggle_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file = None
        self.init_ui()

    def init_ui(self):
        self.setObjectName("conversationSurface")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        toolbar = QFrame()
        toolbar.setObjectName("conversationToolbar")
        toolbar.setFixedHeight(46)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(14, 6, 14, 6)
        toggle = QPushButton(icon("panel"), "")
        toggle.setObjectName("iconButton")
        toggle.setFixedSize(30, 30)
        toggle.setToolTip("Hiện / ẩn danh sách dự án")
        toggle.clicked.connect(self.sidebar_toggle_requested.emit)
        self.sidebar_toggle_button = toggle
        toggle.hide()
        toolbar_layout.addWidget(toggle)
        toolbar_layout.addStretch()
        more = QPushButton(icon("more"), "")
        more.setObjectName("iconButton")
        more.setFixedSize(30, 30)
        more.setToolTip("Tùy chọn hội thoại")
        toolbar_layout.addWidget(more)
        terminal = QPushButton(icon("terminal"), "")
        terminal.setObjectName("iconButton")
        terminal.setFixedSize(30, 30)
        terminal.setToolTip("Terminal (Ctrl+J)")
        terminal.clicked.connect(self.toggle_terminal)
        toolbar_layout.addWidget(terminal)
        self.code_button = QPushButton(icon("code"), "Mở mã nguồn")
        self.code_button.setObjectName("outlineButton")
        self.code_button.clicked.connect(self.search_requested.emit)
        toolbar_layout.addWidget(self.code_button)
        layout.addWidget(toolbar)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)
        self.agent_panel = QWidget()
        self.agent_panel.setObjectName("agentPanel")
        self.agent_panel.setMinimumWidth(360)
        horizontal = QHBoxLayout(self.agent_panel)
        horizontal.setContentsMargins(32, 0, 32, 28)
        horizontal.addStretch()
        self.conversation_column = QWidget()
        self.conversation_column.setObjectName("conversationColumn")
        self.conversation_column.setMaximumWidth(920)
        self.conversation_column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.agent_layout = QVBoxLayout(self.conversation_column)
        self.agent_layout.setContentsMargins(0, 0, 0, 0)
        self.agent_layout.setSpacing(12)
        self.agent_layout.addStretch(1)
        self.top_space = self.agent_layout.itemAt(0)
        self.chat_view = ChatWidget(self)
        conversation_menu = QMenu(more)
        conversation_menu.addAction("Cuộc trò chuyện mới", self.new_conversation_requested.emit)
        conversation_menu.addAction("Lịch sử hội thoại", self.history_requested.emit)
        conversation_menu.addAction("Dọn màn hình trò chuyện", self.chat_view.clear_chat)
        more.setMenu(conversation_menu)
        self.chat_view.content_changed.connect(self.set_conversation_active)
        self.agent_layout.addWidget(self.chat_view, 1)
        self.chat_view.hide()
        self.project_row = QWidget()
        self.project_row.setObjectName("projectSelectorRow")
        project_layout = QHBoxLayout(self.project_row)
        project_layout.setContentsMargins(4, 0, 0, 0)
        self.project_button = QPushButton(icon("folder", "#828282"), "Mở dự án  ⌄")
        self.project_button.setObjectName("projectSelector")
        project_layout.addWidget(self.project_button)
        project_layout.addStretch()
        self.agent_layout.addWidget(self.project_row)
        self.agent_layout.addStretch(1)
        self.bottom_space = self.agent_layout.itemAt(self.agent_layout.count() - 1)
        horizontal.addWidget(self.conversation_column, 1)
        horizontal.addStretch()
        self.splitter.addWidget(self.agent_panel)

        self.workspace = QWidget()
        self.workspace.setObjectName("codeWorkspace")
        self.workspace.setMinimumWidth(280)
        workspace_layout = QVBoxLayout(self.workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)
        code_toolbar = QHBoxLayout()
        code_toolbar.setContentsMargins(12, 4, 6, 4)
        code_toolbar.addWidget(QLabel("Mã nguồn & thay đổi"))
        code_toolbar.addStretch()
        close_code = QPushButton(icon("close"), "")
        close_code.setObjectName("iconButton")
        close_code.setFixedSize(28, 28)
        close_code.setToolTip("Đóng khung mã nguồn")
        close_code.clicked.connect(self.workspace.hide)
        code_toolbar.addWidget(close_code)
        workspace_layout.addLayout(code_toolbar)
        self.pages = QStackedWidget()
        empty = QLabel("Chọn một tệp trong Explorer để xem mã nguồn.")
        empty.setObjectName("emptyState")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setWordWrap(True)
        self.pages.addWidget(empty)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)
        self.code_viewer_tab = QWidget()
        code_layout = QVBoxLayout(self.code_viewer_tab)
        code_layout.setContentsMargins(0, 0, 0, 0)
        self.code_header = QLabel("Chọn một tệp từ Explorer")
        self.code_header.setObjectName("breadcrumb")
        code_layout.addWidget(self.code_header)
        self.code_editor = CodeView()
        code_layout.addWidget(self.code_editor)
        self.tabs.addTab(self.code_viewer_tab, icon("code"), "Mã nguồn")
        self.diff_viewer_tab = QWidget()
        diff_layout = QVBoxLayout(self.diff_viewer_tab)
        diff_layout.setContentsMargins(0, 0, 0, 0)
        self.diff_header = QLabel("Xem lại các thay đổi trước khi áp dụng")
        self.diff_header.setObjectName("breadcrumb")
        diff_layout.addWidget(self.diff_header)
        self.diff_browser = QTextBrowser()
        self.diff_browser.setObjectName("diffBrowser")
        self.diff_browser.setOpenExternalLinks(False)
        diff_layout.addWidget(self.diff_browser)
        self.tabs.addTab(self.diff_viewer_tab, icon("changes"), "Thay đổi")
        self.pages.addWidget(self.tabs)
        workspace_layout.addWidget(self.pages)
        self.splitter.addWidget(self.workspace)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.workspace.hide()
        layout.addWidget(self.splitter, 1)
        self.terminal_view = TerminalWidget(self)
        self.terminal_view.setMinimumHeight(150)
        self.terminal_view.setMaximumHeight(250)
        layout.addWidget(self.terminal_view)
        self.terminal_view.hide()
        self.set_diff("")

    def set_prompt(self, prompt):
        self.agent_layout.insertWidget(self.agent_layout.count() - 1, prompt)

    def set_conversation_active(self, active):
        self.chat_view.setVisible(active)
        for spacer in (self.top_space, self.bottom_space):
            spacer.spacerItem().changeSize(
                0, 0, QSizePolicy.Policy.Minimum,
                QSizePolicy.Policy.Fixed if active else QSizePolicy.Policy.Expanding
            )
        self.agent_layout.invalidate()

    def show_chat(self):
        self.agent_panel.show()
        self.set_conversation_active(bool(self.chat_view.chat_history))

    def show_terminal(self):
        self.terminal_view.show()
        self.terminal_view.cmd_input.setFocus()

    def toggle_terminal(self):
        if self.terminal_view.isVisible():
            self.terminal_view.hide()
        else:
            self.show_terminal()

    def show_code(self):
        self.workspace.show()
        self.splitter.setSizes([560, 420])

    def set_file_content(self, path: str, content: str, line_number: int = None):
        self.current_file = path
        self.code_header.setText(path.replace("\\", "/").replace("/", "  ›  "))
        self.code_header.setToolTip(path)
        self.code_editor.highlighter.enabled = path.lower().endswith((".py", ".pyw"))
        self.code_editor.setPlainText(content)
        self.tabs.setTabText(0, os.path.basename(path))
        self.tabs.setTabToolTip(0, path)
        self.pages.setCurrentWidget(self.tabs)
        self.tabs.setCurrentWidget(self.code_viewer_tab)
        self.show_code()
        if line_number is not None and line_number > 0:
            block = self.code_editor.document().findBlockByNumber(line_number - 1)
            if block.isValid():
                self.code_editor.setTextCursor(QTextCursor(block))
                self.code_editor.centerCursor()

    def set_diff(self, diff_text: str):
        self.diff_browser.setHtml(format_diff_html(diff_text))
        if diff_text and diff_text.strip():
            self.pages.setCurrentWidget(self.tabs)
            self.tabs.setCurrentWidget(self.diff_viewer_tab)
            self.show_code()
