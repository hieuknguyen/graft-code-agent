"""Conversation workspace styled after the supplied Antigravity reference."""

DARK_STYLESHEET = """
QWidget { background: #101010; color: #bcbcbc; font-family: "Segoe UI", "Inter", "DejaVu Sans"; font-size: 14px; selection-background-color: #3a3a3a; selection-color: #eeeeee; }
QMainWindow, QWidget#workbench, QWidget#conversationSurface, QWidget#agentPanel, QWidget#conversationColumn, QWidget#projectSelectorRow { background: #101010; }
QWidget#sidebar, QWidget#sidebarPage { background: #171717; }
QStackedWidget { background: transparent; }
QLabel { background: transparent; border: none; }
QLabel#brand { font-size: 16px; color: #d0d0d0; font-weight: 500; margin-left: 5px; }
QLabel#muted { color: #777777; font-size: 11px; }
QLabel#sectionLabel { color: #777777; font-size: 12px; font-weight: 600; padding: 0 8px; }
QLabel#emptyState { color: #707070; padding: 20px; }
QLabel#breadcrumb { color: #929292; font-size: 11px; padding: 7px 12px; }
QWidget#codeWorkspace { background: #161616; border-left: 1px solid #262626; }
QFrame#conversationToolbar { background: #101010; border: none; }
QSplitter::handle { background: #202020; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }
QSplitter::handle:hover { background: #505050; }
QMenuBar { background: #171717; color: #9b9b9b; padding: 5px 10px; }
QMenuBar::item { padding: 4px 12px; background: transparent; }
QMenuBar::item:selected { background: #2b2b2b; border-radius: 4px; }
QMenu { background: #242424; border: 1px solid #393939; padding: 5px; }
QMenu::item { padding: 8px 28px 8px 12px; border-radius: 4px; }
QMenu::item:selected { background: #343434; }
QMenu::separator { height: 1px; background: #393939; margin: 5px; }
QStatusBar { background: #171717; color: #777777; font-size: 11px; }
QStatusBar::item { border: none; }
QToolTip { background: #303030; color: #dedede; border: 1px solid #454545; padding: 5px 8px; }
QPushButton, QToolButton { background: #292929; color: #bcbcbc; border: 1px solid #383838; border-radius: 7px; padding: 6px 10px; font-weight: 400; }
QPushButton:hover, QToolButton:hover { background: #323232; border-color: #484848; color: #eeeeee; }
QPushButton:pressed, QToolButton:pressed { background: #3a3a3a; }
QPushButton:disabled { color: #626262; background: #242424; border-color: #2b2b2b; }
QPushButton:focus { border-color: #696969; }
QPushButton#navButton { background: transparent; border: 1px solid transparent; text-align: left; padding: 9px 10px; border-radius: 8px; font-size: 15px; }
QPushButton#navButton:hover { background: #242424; }
QPushButton#newConversation { background: #303030; color: #dddddd; border: 1px solid #3b3b3b; border-radius: 9px; padding: 7px 12px; text-align: left; font-size: 14px; }
QPushButton#newConversation:hover { background: #393939; }
QPushButton#iconButton { background: transparent; border: 1px solid transparent; padding: 4px; border-radius: 5px; }
QPushButton#iconButton:hover { background: #292929; }
QPushButton#outlineButton { background: transparent; border: 1px solid #272727; color: #ababab; padding: 6px 10px; }
QPushButton#outlineButton:hover { background: #242424; }
QPushButton#projectSelector { background: transparent; border: none; color: #828282; font-size: 14px; padding: 5px 8px; text-align: left; }
QPushButton#projectSelector:hover { background: #202020; color: #c5c5c5; }
QPushButton#modelButton { background: transparent; border: none; color: #a5a5a5; text-align: left; padding: 4px 0; font-size: 13px; }
QPushButton#modelButton:hover { color: #eeeeee; }
QPushButton#subtleButton { background: transparent; border: none; color: #858585; font-size: 11px; padding: 3px 4px; }
QPushButton#subtleButton:hover { color: #cccccc; }
QPushButton#sendButton { background: #303030; border: none; border-radius: 17px; padding: 7px; }
QPushButton#sendButton:hover { background: #484848; }
QPushButton#sendButton:disabled { background: #232323; }
QPushButton#successButton { background: #29362c; border-color: #3c4d3f; color: #bad0be; }
QPushButton#successButton:disabled { background: #242424; color: #626262; border-color: #2b2b2b; }
QLineEdit, QPlainTextEdit, QTextBrowser { background: #191919; color: #d0d0d0; border: 1px solid #343434; border-radius: 6px; padding: 7px; }
QLineEdit:focus { border-color: #696969; }
QLineEdit#sidebarSearch { background: #222222; padding: 8px; }
QPlainTextEdit#codeEditor, QTextBrowser#diffBrowser, QTextBrowser#terminalOutput { background: #161616; border: none; border-radius: 0; padding: 10px; font-family: "Cascadia Code", "Consolas", "DejaVu Sans Mono"; font-size: 12px; }
QTextBrowser#chatBrowser { background: #101010; border: none; border-radius: 0; padding: 8px 0; }
QFrame#composer { background: #242424; border: none; border-radius: 18px; }
QFrame#composerBody { background: #1d1d1d; border: 1px solid #292929; border-radius: 18px; }
QPlainTextEdit#promptInput { background: transparent; border: none; padding: 4px 0; font-size: 15px; color: #dddddd; }
QWidget#promptPanel, QWidget#promptActions { background: transparent; }
QWidget#composerFooter { background: transparent; border: none; }
QWidget#promptOptions { background: #1a1a1a; border-radius: 8px; }
QComboBox { background: #252525; border: 1px solid #383838; border-radius: 5px; padding: 5px 8px; min-height: 18px; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView { background: #252525; border: 1px solid #484848; selection-background-color: #393939; }
QCheckBox { background: transparent; color: #aaaaaa; spacing: 6px; font-size: 11px; }
QCheckBox::indicator { width: 13px; height: 13px; border: 1px solid #5a5a5a; border-radius: 3px; background: #202020; }
QCheckBox::indicator:checked { background: #bcbcbc; border: 3px solid #565656; }
QTabWidget::pane { background: #161616; border: none; }
QTabBar { background: #171717; }
QTabBar::tab { background: #171717; color: #888888; border-bottom: 1px solid transparent; padding: 9px 14px; }
QTabBar::tab:selected { color: #eeeeee; border-bottom: 1px solid #bbbbbb; }
QTreeWidget, QListWidget { background: transparent; border: none; outline: none; padding: 0; }
QTreeWidget::item { padding: 5px 2px; border: none; }
QTreeWidget#projectTree::item { height: 31px; padding: 4px 6px; border-radius: 5px; }
QListWidget#recentConversations::item { height: 29px; padding: 4px 8px; border-radius: 5px; }
QTreeWidget::item:hover, QListWidget::item:hover { background: #242424; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #292929; color: #d6d6d6; }
QHeaderView::section { background: #171717; color: #929292; border: none; padding: 6px; font-size: 11px; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { border: none; background: transparent; width: 7px; margin: 0; }
QScrollBar::handle:vertical { background: #3b3b3b; min-height: 24px; border-radius: 3px; }
QScrollBar::handle:vertical:hover { background: #555555; }
QScrollBar:horizontal { border: none; background: transparent; height: 7px; margin: 0; }
QScrollBar::handle:horizontal { background: #3b3b3b; min-width: 24px; border-radius: 3px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""

def format_diff_html(diff_text: str) -> str:
    """Format unified diff text into modern color-highlighted HTML."""
    if not diff_text or not diff_text.strip():
        return "<div style='color:#9699a3; padding:20px; font-family:Consolas, monospace;'>Chưa có kết quả cấy ghép hoặc không có sự thay đổi.</div>"

    lines = diff_text.splitlines()
    html_lines = [
        "<div style='font-family: Consolas, monospace; font-size: 12px; line-height: 1.5; background-color:#161616; padding: 12px; border-radius: 6px; white-space: pre-wrap;'>"
    ]
    for line in lines:
        escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if line.startswith("+++") or line.startswith("---"):
            html_lines.append(f"<div style='color: #a4a7af; font-weight: bold;'>{escaped}</div>")
        elif line.startswith("@@"):
            html_lines.append(f"<div style='background-color: rgba(56, 189, 248, 0.12); color: #aecbfa; font-weight: bold; padding: 2px 4px; border-radius: 3px; margin: 2px 0;'>{escaped}</div>")
        elif line.startswith("+"):
            html_lines.append(f"<div style='background-color: rgba(34, 197, 94, 0.16); color: #a8dab5; padding: 1px 4px; border-left: 3px solid #22c55e;'>{escaped}</div>")
        elif line.startswith("-"):
            html_lines.append(f"<div style='background-color: rgba(239, 68, 68, 0.16); color: #f4b4b4; padding: 1px 4px; border-left: 3px solid #ef4444;'>{escaped}</div>")
        else:
            html_lines.append(f"<div style='color: #c4c7cf; padding: 1px 4px;'>{escaped}</div>")
    html_lines.append("</div>")
    return "".join(html_lines)
