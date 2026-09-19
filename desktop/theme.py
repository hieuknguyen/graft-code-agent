"""
Modern Dark Theme QSS for Graft Code Agent Desktop App.
Styling inspired by modern AI IDEs (VS Code / Windsurf / Cursor).
"""

DARK_STYLESHEET = """
/* Global Styles */
QWidget {
    background-color: #0b0f19;
    color: #e2e8f0;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 13px;
    selection-background-color: #4f46e5;
    selection-color: #ffffff;
}

/* Main Window & Panels */
QMainWindow {
    background-color: #0b0f19;
}

QSplitter::handle {
    background-color: #1e293b;
}
QSplitter::handle:horizontal {
    width: 2px;
}
QSplitter::handle:vertical {
    height: 2px;
}
QSplitter::handle:hover {
    background-color: #6366f1;
}

/* Menu Bar */
QMenuBar {
    background-color: #0f172a;
    border-bottom: 1px solid #1e293b;
    padding: 2px 6px;
    color: #cbd5e1;
}
QMenuBar::item {
    background: transparent;
    padding: 5px 10px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background-color: #1e293b;
    color: #ffffff;
}
QMenu {
    background-color: #0f172a;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #4f46e5;
    color: #ffffff;
}
QMenu::separator {
    height: 1px;
    background-color: #1e293b;
    margin: 4px 0;
}

/* ToolBar & Status Bar */
QToolBar {
    background-color: #0f172a;
    border-bottom: 1px solid #1e293b;
    padding: 4px 8px;
    spacing: 6px;
}
QStatusBar {
    background-color: #0f172a;
    border-top: 1px solid #1e293b;
    color: #94a3b8;
    font-size: 12px;
    padding: 2px 8px;
}

/* Tree Widget (AST Explorer) */
QTreeWidget {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 4px;
    outline: none;
}
QTreeWidget::item {
    padding: 5px 6px;
    border-radius: 4px;
    margin: 1px 0;
}
QTreeWidget::item:hover {
    background-color: #1e293b;
    color: #f8fafc;
}
QTreeWidget::item:selected {
    background-color: #312e81;
    color: #ffffff;
}
QHeaderView::section {
    background-color: #0f172a;
    color: #94a3b8;
    padding: 6px;
    border: none;
    border-bottom: 1px solid #1e293b;
    font-weight: 600;
}

/* Tab Widget */
QTabWidget::pane {
    border: 1px solid #1e293b;
    background-color: #0f172a;
    border-radius: 8px;
    top: -1px;
}
QTabBar::tab {
    background-color: #0f172a;
    color: #94a3b8;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background-color: #1e293b;
    color: #818cf8;
    border-bottom: 2px solid #6366f1;
}
QTabBar::tab:hover:!selected {
    background-color: #131d31;
    color: #cbd5e1;
}

/* Text Editors & Inputs */
QPlainTextEdit, QTextBrowser, QLineEdit {
    background-color: #090d16;
    border: 1px solid #1e293b;
    border-radius: 6px;
    color: #f8fafc;
    padding: 8px;
    selection-background-color: #4338ca;
}
QPlainTextEdit:focus, QTextBrowser:focus, QLineEdit:focus {
    border: 1px solid #6366f1;
}

/* ComboBox */
QComboBox {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 6px;
    padding: 5px 10px;
    color: #e2e8f0;
    min-height: 22px;
}
QComboBox:hover {
    border: 1px solid #475569;
}
QComboBox:focus {
    border: 1px solid #6366f1;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #0f172a;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 4px;
    selection-background-color: #4f46e5;
    color: #f8fafc;
}

/* CheckBox */
QCheckBox {
    color: #cbd5e1;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #334155;
    background-color: #0f172a;
}
QCheckBox::indicator:checked {
    background-color: #6366f1;
    border-color: #6366f1;
}
QCheckBox::indicator:hover {
    border-color: #6366f1;
}

/* Buttons */
QPushButton {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    color: #f8fafc;
    padding: 6px 14px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #334155;
    border-color: #475569;
}
QPushButton:pressed {
    background-color: #0f172a;
}
QPushButton:disabled {
    background-color: #0f172a;
    border-color: #1e293b;
    color: #475569;
}

/* Primary Button (Accent Indigo) */
QPushButton#primaryButton {
    background-color: #4f46e5;
    border: 1px solid #6366f1;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#primaryButton:hover {
    background-color: #4338ca;
}
QPushButton#primaryButton:pressed {
    background-color: #3730a3;
}
QPushButton#primaryButton:disabled {
    background-color: #1e1b4b;
    border-color: #312e81;
    color: #64748b;
}

/* Success Button (Green Apply) */
QPushButton#successButton {
    background-color: #15803d;
    border: 1px solid #22c55e;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#successButton:hover {
    background-color: #166534;
}
QPushButton#successButton:disabled {
    background-color: #052e16;
    border-color: #14532d;
    color: #475569;
}

/* Danger / Undo Button */
QPushButton#undoButton {
    background-color: #334155;
    border: 1px solid #eab308;
    color: #fef08a;
    font-weight: 600;
}
QPushButton#undoButton:hover {
    background-color: #475569;
}
QPushButton#undoButton:disabled {
    background-color: #0f172a;
    border-color: #1e293b;
    color: #475569;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background-color: #0b0f19;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #1e293b;
    min-height: 24px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background-color: #334155;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    border: none;
    background-color: #0b0f19;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background-color: #1e293b;
    min-width: 24px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #334155;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* Tooltips */
QToolTip {
    background-color: #0f172a;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}
"""

def format_diff_html(diff_text: str) -> str:
    """Format unified diff text into modern color-highlighted HTML."""
    if not diff_text or not diff_text.strip():
        return "<div style='color:#64748b; padding:20px; font-family:Consolas, monospace;'>Chưa có kết quả cấy ghép hoặc không có sự thay đổi.</div>"

    lines = diff_text.splitlines()
    html_lines = [
        "<div style='font-family: Consolas, monospace; font-size: 12px; line-height: 1.5; background-color:#090d16; padding: 12px; border-radius: 6px; white-space: pre-wrap;'>"
    ]
    for line in lines:
        escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if line.startswith("+++") or line.startswith("---"):
            html_lines.append(f"<div style='color: #94a3b8; font-weight: bold;'>{escaped}</div>")
        elif line.startswith("@@"):
            html_lines.append(f"<div style='background-color: rgba(56, 189, 248, 0.12); color: #38bdf8; font-weight: bold; padding: 2px 4px; border-radius: 3px; margin: 2px 0;'>{escaped}</div>")
        elif line.startswith("+"):
            html_lines.append(f"<div style='background-color: rgba(34, 197, 94, 0.16); color: #4ade80; padding: 1px 4px; border-left: 3px solid #22c55e;'>{escaped}</div>")
        elif line.startswith("-"):
            html_lines.append(f"<div style='background-color: rgba(239, 68, 68, 0.16); color: #f87171; padding: 1px 4px; border-left: 3px solid #ef4444;'>{escaped}</div>")
        else:
            html_lines.append(f"<div style='color: #cbd5e1; padding: 1px 4px;'>{escaped}</div>")
    html_lines.append("</div>")
    return "".join(html_lines)
