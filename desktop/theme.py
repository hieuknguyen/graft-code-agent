"""Neutral IDE surfaces inspired by the Antigravity desktop layout."""

DARK_STYLESHEET = """
QWidget { background: #1b1c20; color: #e3e3e8; font-family: "Segoe UI", "Inter", "DejaVu Sans"; font-size: 12px; selection-background-color: #35455f; selection-color: #ffffff; }
QMainWindow, QWidget#workbench { background: #18191d; }
QWidget#activityBar { background: #18191d; border-right: 1px solid #303136; }
QWidget#sidebar, QWidget#agentPanel { background: #202126; }
QFrame#commandBar { background: #18191d; border-bottom: 1px solid #303136; }
QLabel { background: transparent; border: none; }
QLabel#muted, QLabel#sectionLabel { color: #9699a3; font-size: 11px; }
QLabel#sectionLabel { font-weight: 600; }
QLabel#brand { color: #e8eaed; font-weight: 600; font-size: 14px; }
QLabel#welcomeTitle { color: #e8eaed; font-size: 32px; font-weight: 600; }
QLabel#welcomeSubtitle { color: #9699a3; font-size: 13px; }
QLabel#breadcrumb { color: #9699a3; padding: 7px 12px; font-size: 11px; }
QFrame#panelHeader { background: #202126; border-bottom: 1px solid #303136; }
QSplitter::handle { background: #303136; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }
QSplitter::handle:hover { background: #8ab4f8; }
QMenuBar { background: #18191d; color: #aaaeb7; padding: 2px 8px; }
QMenuBar::item { padding: 4px 10px; background: transparent; }
QMenuBar::item:selected { background: #2b2d34; border-radius: 4px; }
QMenu { background: #25262c; border: 1px solid #3b3e47; padding: 5px; }
QMenu::item { padding: 7px 26px 7px 12px; border-radius: 4px; }
QMenu::item:selected { background: #363941; }
QMenu::separator { height: 1px; background: #3b3e47; margin: 5px; }
QStatusBar { background: #18191d; border-top: 1px solid #303136; color: #9699a3; font-size: 11px; }
QStatusBar::item { border: none; }
QToolTip { background: #30323a; color: #e8eaed; border: 1px solid #484b56; padding: 5px 8px; }
QPushButton, QToolButton { background: #2b2d34; color: #d5d7de; border: 1px solid #3b3e47; border-radius: 5px; padding: 5px 10px; font-weight: 500; }
QPushButton:hover, QToolButton:hover { background: #363941; border-color: #505460; }
QPushButton:pressed, QToolButton:pressed { background: #40444e; }
QPushButton:disabled, QToolButton:disabled { color: #60646f; background: #25262c; border-color: #303136; }
QPushButton:focus, QToolButton:focus { border-color: #8ab4f8; }
QPushButton#iconButton, QToolButton#iconButton { background: transparent; border: 1px solid transparent; padding: 5px; }
QPushButton#iconButton:hover, QToolButton#iconButton:hover { background: #33353d; }
QPushButton#activityButton { background: transparent; border: none; border-left: 2px solid transparent; border-radius: 0; padding: 10px; }
QPushButton#activityButton:hover { background: #25262c; }
QPushButton#activityButton:checked { background: #25272d; border-left: 2px solid #aecbfa; }
QPushButton#primaryButton { background: #aecbfa; color: #172338; border: 1px solid #aecbfa; font-weight: 600; }
QPushButton#primaryButton:hover { background: #c5dafa; }
QPushButton#primaryButton:disabled { background: #323945; color: #727c8c; border-color: #3b414c; }
QPushButton#successButton { background: #263c33; color: #a8dab5; border-color: #3c5648; }
QPushButton#successButton:hover { background: #304b3f; }
QPushButton#successButton:disabled { background: #25262c; color: #60646f; border-color: #303136; }
QPushButton#commandSearch { background: #23252b; color: #b1b4bd; border-color: #383b44; text-align: left; padding: 5px 14px; }
QPushButton#welcomeAction { background: transparent; border: none; text-align: left; padding: 10px 14px; color: #b7c9e8; }
QPushButton#welcomeAction:hover { background: #272a31; }
QPushButton#modelButton { background: transparent; border: none; color: #aebbd2; text-align: left; padding: 5px 0; }
QPushButton#modelButton:hover { color: #d2e3fc; }
QLineEdit, QPlainTextEdit, QTextBrowser { background: #1b1c20; color: #d5d7de; border: 1px solid #363941; border-radius: 5px; padding: 7px; }
QLineEdit:focus, QPlainTextEdit:focus { border-color: #6984ab; }
QLineEdit#sidebarSearch { background: #25262c; padding: 6px 8px; }
QPlainTextEdit#codeEditor, QTextBrowser#diffBrowser, QTextBrowser#terminalOutput { background: #1b1c20; border: none; border-radius: 0; padding: 10px; font-family: "Cascadia Code", "Consolas", "DejaVu Sans Mono"; font-size: 12px; }
QTextBrowser#chatBrowser { background: #202126; border: none; border-radius: 0; padding: 14px; }
QFrame#composer { background: #282a30; border: 1px solid #414550; border-radius: 10px; }
QPlainTextEdit#promptInput { background: transparent; border: none; padding: 4px; font-size: 13px; }
QWidget#promptPanel, QWidget#promptOptions { background: #202126; }
QWidget#composerTools { background: transparent; }
QComboBox { background: #272930; border: 1px solid #3b3e47; border-radius: 5px; padding: 5px 8px; min-height: 18px; }
QComboBox:hover { border-color: #5b616e; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView { background: #272930; border: 1px solid #484c57; selection-background-color: #35455f; }
QCheckBox { background: transparent; color: #b5b8c2; spacing: 6px; font-size: 11px; }
QCheckBox::indicator { width: 13px; height: 13px; border: 1px solid #5a5e68; border-radius: 3px; background: #202126; }
QCheckBox::indicator:checked { background: #aecbfa; border: 3px solid #526b90; }
QTabWidget::pane { background: #1b1c20; border: none; }
QTabBar { background: #202126; }
QTabBar::tab { background: #202126; color: #9699a3; border: none; border-bottom: 2px solid transparent; padding: 9px 14px; }
QTabBar::tab:selected { background: #1b1c20; color: #e8eaed; border-bottom: 2px solid #aecbfa; }
QTabBar::tab:hover:!selected { background: #2a2c33; color: #d5d7de; }
QTreeWidget, QListWidget { background: transparent; border: none; outline: none; padding: 3px 0; }
QTreeWidget::item { padding: 4px 2px; border: none; }
QListWidget::item { padding: 9px 8px; border: none; border-radius: 4px; margin: 1px 0; }
QTreeWidget::item:hover, QListWidget::item:hover { background: #2c2e35; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #333740; color: #e8eaed; }
QHeaderView::section { background: #202126; color: #9699a3; border: none; padding: 6px; font-size: 11px; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { border: none; background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #40434c; min-height: 24px; border-radius: 4px; }
QScrollBar::handle:vertical:hover { background: #565b68; }
QScrollBar:horizontal { border: none; background: transparent; height: 8px; margin: 0; }
QScrollBar::handle:horizontal { background: #40434c; min-width: 24px; border-radius: 4px; }
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
        "<div style='font-family: Consolas, monospace; font-size: 12px; line-height: 1.5; background-color:#1b1c20; padding: 12px; border-radius: 6px; white-space: pre-wrap;'>"
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
