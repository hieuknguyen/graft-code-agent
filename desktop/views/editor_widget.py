import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTextBrowser,
    QLabel, QPushButton, QSplitter, QStackedWidget, QFrame
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)
        self.workspace = QSplitter(Qt.Orientation.Vertical)
        self.workspace.setChildrenCollapsible(False)
        self.workspace.setHandleWidth(1)
        self.workspace.setMinimumWidth(280)
        self.pages = QStackedWidget()

        welcome = QWidget()
        welcome_layout = QVBoxLayout(welcome)
        welcome_layout.setContentsMargins(30, 30, 30, 30)
        welcome_layout.addStretch()
        mark = QLabel()
        mark.setPixmap(icon('spark', '#697381', 64).pixmap(64, 64))
        welcome_layout.addWidget(mark, alignment=Qt.AlignmentFlag.AlignHCenter)
        title = QLabel('Graft')
        title.setObjectName('welcomeTitle')
        welcome_layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)
        subtitle = QLabel('Không gian cho ý tưởng của bạn.')
        subtitle.setObjectName('welcomeSubtitle')
        welcome_layout.addWidget(subtitle, alignment=Qt.AlignmentFlag.AlignHCenter)
        welcome_layout.addSpacing(22)
        for name, text, signal in (
            ('folder', 'Mở thư mục                         Ctrl+O', self.open_folder_requested),
            ('search', 'Tìm tệp                                Ctrl+P', self.search_requested),
            ('spark', 'Hỏi Agent                            Ctrl+L', self.focus_agent_requested),
        ):
            button = QPushButton(icon(name), text)
            button.setObjectName('welcomeAction')
            button.setMaximumWidth(330)
            button.clicked.connect(signal.emit)
            welcome_layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignHCenter)
        welcome_layout.addStretch()
        self.pages.addWidget(welcome)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)
        self.code_viewer_tab = QWidget()
        code_layout = QVBoxLayout(self.code_viewer_tab)
        code_layout.setContentsMargins(0, 0, 0, 0)
        code_layout.setSpacing(0)
        self.code_header = QLabel('Chọn một tệp từ Explorer')
        self.code_header.setObjectName('breadcrumb')
        code_layout.addWidget(self.code_header)
        self.code_editor = CodeView()
        code_layout.addWidget(self.code_editor)
        self.tabs.addTab(self.code_viewer_tab, icon('code'), 'Mã nguồn')

        self.diff_viewer_tab = QWidget()
        diff_layout = QVBoxLayout(self.diff_viewer_tab)
        diff_layout.setContentsMargins(0, 0, 0, 0)
        diff_layout.setSpacing(0)
        self.diff_header = QLabel('Xem lại các thay đổi trước khi áp dụng')
        self.diff_header.setObjectName('breadcrumb')
        diff_layout.addWidget(self.diff_header)
        self.diff_browser = QTextBrowser()
        self.diff_browser.setObjectName('diffBrowser')
        self.diff_browser.setOpenExternalLinks(False)
        diff_layout.addWidget(self.diff_browser)
        self.tabs.addTab(self.diff_viewer_tab, icon('changes'), 'Thay đổi')
        self.pages.addWidget(self.tabs)
        self.workspace.addWidget(self.pages)
        self.terminal_view = TerminalWidget(self)
        self.terminal_view.setMinimumHeight(140)
        self.workspace.addWidget(self.terminal_view)
        self.workspace.setSizes([580, 190])
        self.splitter.addWidget(self.workspace)

        self.agent_panel = QWidget()
        self.agent_panel.setObjectName('agentPanel')
        self.agent_panel.setMinimumWidth(340)
        self.agent_layout = QVBoxLayout(self.agent_panel)
        self.agent_layout.setContentsMargins(0, 0, 0, 0)
        self.agent_layout.setSpacing(0)
        header = QFrame()
        header.setObjectName('panelHeader')
        header.setFixedHeight(39)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 2, 8, 2)
        header_layout.addWidget(QLabel('Agent'))
        header_layout.addStretch()
        for name, label, signal in (
            ('plus', 'Cuộc trò chuyện mới (Ctrl+N)', self.new_conversation_requested),
            ('chat', 'Lịch sử trò chuyện', self.history_requested),
        ):
            button = QPushButton(icon(name), '')
            button.setObjectName('iconButton')
            button.setFixedSize(28, 28)
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.clicked.connect(signal.emit)
            header_layout.addWidget(button)
        self.agent_layout.addWidget(header)
        self.chat_view = ChatWidget(self)
        header_layout.addWidget(self.chat_view.btn_clear)
        self.agent_layout.addWidget(self.chat_view, 1)
        self.splitter.addWidget(self.agent_panel)
        self.splitter.setSizes([660, 390])
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        layout.addWidget(self.splitter)
        self.set_diff('')

    def set_prompt(self, prompt):
        self.agent_layout.addWidget(prompt)

    def show_chat(self):
        self.agent_panel.show()

    def show_terminal(self):
        self.terminal_view.show()
        self.terminal_view.cmd_input.setFocus()

    def set_file_content(self, path: str, content: str, line_number: int = None):
        self.current_file = path
        self.code_header.setText(path.replace('\\', '/').replace('/', '  ›  '))
        self.code_header.setToolTip(path)
        self.code_editor.highlighter.enabled = path.lower().endswith(('.py', '.pyw'))
        self.code_editor.setPlainText(content)
        self.tabs.setTabText(0, os.path.basename(path))
        self.tabs.setTabToolTip(0, path)
        self.pages.setCurrentWidget(self.tabs)
        self.tabs.setCurrentWidget(self.code_viewer_tab)
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
