import re
from urllib.parse import quote, unquote
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser,
    QPushButton, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QTextCursor

class ChatWidget(QWidget):
    action_apply_clicked = Signal(dict)
    action_view_diff_clicked = Signal(dict)
    action_run_command_clicked = Signal(str)
    action_create_file_clicked = Signal(str)
    action_delete_file_clicked = Signal(str)
    message_persisted = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.chat_history: List[str] = []
        self.raw_messages: List[Dict[str, Any]] = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        header = QHBoxLayout()
        icon = QLabel("💬")
        icon.setStyleSheet("font-size: 15px;")
        header.addWidget(icon)

        title = QLabel("TRỢ LÝ AI AGENT (HỎI ĐÁP & ĐIỀU PHỐI DỰ ÁN)")
        title.setStyleSheet("font-weight: bold; color: #818cf8; font-size: 12px;")
        header.addWidget(title)
        header.addStretch()

        self.btn_clear = QPushButton("🗑️ Xóa Hội Thoại")
        self.btn_clear.clicked.connect(self.clear_chat)
        header.addWidget(self.btn_clear)
        layout.addLayout(header)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.browser.anchorClicked.connect(self.on_link_clicked)
        self.browser.setStyleSheet("""
            QTextBrowser {
                background-color: #070a13;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 12px;
                font-family: 'Segoe UI', -apple-system, sans-serif;
                font-size: 13px;
                line-height: 1.6;
            }
        """)
        layout.addWidget(self.browser)

        self.render_all()

    def markdown_to_html(self, text: str) -> str:
        def code_block_repl(m):
            code_content = m.group(1).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            return f"<pre style='background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 10px; font-family: Consolas, monospace; font-size: 12px; color: #cbd5e1; overflow-x: auto;'>{code_content}</pre>"
        
        t = re.sub(r'```(?:[a-zA-Z0-9_-]+)?\s*\n(.*?)```', code_block_repl, text, flags=re.DOTALL)
        t = re.sub(r'`([^`]+)`', r"<code style='background-color: #1e293b; color: #a5b4fc; padding: 2px 5px; border-radius: 4px; font-family: Consolas, monospace; font-size: 12px;'>\1</code>", t)
        t = re.sub(r'^### (.*?)$', r"<h3 style='color: #818cf8; font-size: 14px; margin: 12px 0 6px 0; font-weight: bold;'>\1</h3>", t, flags=re.MULTILINE)
        t = re.sub(r'^## (.*?)$', r"<h2 style='color: #a5b4fc; font-size: 16px; margin: 14px 0 8px 0; font-weight: bold; border-bottom: 1px solid #1e293b; padding-bottom: 4px;'>\1</h2>", t, flags=re.MULTILINE)
        t = re.sub(r'^# (.*?)$', r"<h1 style='color: #c7d2fe; font-size: 18px; margin: 16px 0 10px 0; font-weight: 800;'>\1</h1>", t, flags=re.MULTILINE)
        t = re.sub(r'\*\*(.*?)\*\*', r"<b>\1</b>", t)
        t = re.sub(r'\*(.*?)\*', r"<i>\1</i>", t)
        t = re.sub(r'^[ \t]*[-*] (.*?)$', r"<li style='margin-left: 16px; color: #e2e8f0;'>\1</li>", t, flags=re.MULTILINE)

        lines = t.splitlines()
        formatted_lines = []
        for line in lines:
            if line.startswith("<h") or line.startswith("<pre") or line.startswith("<li") or line.strip() == "":
                formatted_lines.append(line)
            else:
                formatted_lines.append(f"<p style='margin: 4px 0; color: #cbd5e1;'>{line}</p>")

        return "\n".join(formatted_lines)

    def add_user_message(self, text: str, images: Optional[List[str]] = None, persist: bool = True):
        msg_dict = {"role": "user", "text": text, "images": images or []}
        if persist:
            self.raw_messages.append(msg_dict)
            self.message_persisted.emit(msg_dict)

        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        images_html = ""
        if images:
            img_tags = ""
            for img_uri in images:
                img_tags += f"<div style='margin-top: 8px;'><img src='{img_uri}' style='max-width: 320px; max-height: 220px; border-radius: 6px; border: 1px solid #4f46e5;' /></div>"
            images_html = f"<div style='margin-top: 6px;'>{img_tags}</div>"

        msg_html = f"""
        <div style='margin-bottom: 16px; display: flex; justify-content: flex-end;'>
            <div style='background-color: #1e1b4b; border: 1px solid #4338ca; border-radius: 8px; padding: 10px 14px; max-width: 85%; color: #e0e7ff;'>
                <div style='font-size: 11px; font-weight: bold; color: #a5b4fc; margin-bottom: 4px;'>🧑 Bạn:</div>
                <div style='white-space: pre-wrap; font-size: 13px;'>{escaped}</div>
                {images_html}
            </div>
        </div>
        """
        self.chat_history.append(msg_html)
        self.render_all()

    def add_ai_message(self, text: str, graft_actions: List[dict] = None, create_files: List[dict] = None,
                       delete_files: List[dict] = None, commands: List[dict] = None, tokens: dict = None, persist: bool = True, auto_applied: bool = False):
        msg_dict = {
            "role": "ai",
            "text": text,
            "graft_actions": graft_actions,
            "create_files": create_files,
            "delete_files": delete_files,
            "commands": commands,
            "tokens": tokens
        }
        if persist:
            self.raw_messages.append(msg_dict)
            self.message_persisted.emit(msg_dict)

        content_html = self.markdown_to_html(text)

        cards_html = ""
        if graft_actions:
            for act in graft_actions:
                if act.get("success"):
                    f = act['file']
                    if auto_applied:
                        cards_html += f"""
                        <div style='margin-top: 10px; background-color: #0f172a; border: 1px solid #22c55e; border-radius: 6px; padding: 10px;'>
                            <div style='color: #4ade80; font-weight: bold;'>💾 Đã tự động cấy ghép AST vào: <code>{f}</code></div>
                            <div style='color: #94a3b8; font-size: 11px; margin: 4px 0;'>{act.get('msg', '')}</div>
                            <div style='margin-top: 6px;'>
                                <a href='graftview:///{quote(f)}' style='background-color: #1e293b; color: #38bdf8; text-decoration: none; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold; margin-right: 8px;'>🔍 Xem Diff Chi Tiết</a>
                                <span style='color: #22c55e; font-size: 11px; font-weight: bold;'>✅ Đã lưu trực tiếp vào file</span>
                            </div>
                        </div>
                        """
                    else:
                        cards_html += f"""
                        <div style='margin-top: 10px; background-color: #0f172a; border: 1px solid #22c55e; border-radius: 6px; padding: 10px;'>
                            <div style='color: #4ade80; font-weight: bold;'>⚡ Đã chuẩn bị cấy ghép AST vào: <code>{f}</code></div>
                            <div style='color: #94a3b8; font-size: 11px; margin: 4px 0;'>{act.get('msg', '')}</div>
                            <div style='margin-top: 6px;'>
                                <a href='graftview:///{quote(f)}' style='background-color: #1e293b; color: #38bdf8; text-decoration: none; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold; margin-right: 8px;'>🔍 Xem Diff Chi Tiết</a>
                                <a href='graftapply:///{quote(f)}' style='background-color: #15803d; color: #ffffff; text-decoration: none; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold;'>💾 Áp Dụng Ngay</a>
                            </div>
                        </div>
                        """
                else:
                    cards_html += f"""
                    <div style='margin-top: 10px; background-color: #450a0a; border: 1px solid #ef4444; border-radius: 6px; padding: 10px; color: #fca5a5;'>
                        ❌ <b>Cấy ghép thất bại trên {act['file']}:</b> {act.get('error', '')}
                    </div>
                    """

        if create_files:
            for cf in create_files:
                f = cf['file']
                if auto_applied:
                    cards_html += f"""
                    <div style='margin-top: 10px; background-color: #0f172a; border: 1px solid #6366f1; border-radius: 6px; padding: 10px;'>
                        <div style='color: #818cf8; font-weight: bold;'>📝 Đã tự động tạo file: <code>{f}</code></div>
                        <div style='margin-top: 6px;'>
                            <a href='open_file:{quote(f)}' style='background-color: #4f46e5; color: #ffffff; text-decoration: none; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold;'>📄 Mở xem file</a>
                            <span style='color: #22c55e; font-size: 11px; font-weight: bold; margin-left: 8px;'>✅ Đã tạo thành công</span>
                        </div>
                    </div>
                    """
                else:
                    cards_html += f"""
                    <div style='margin-top: 10px; background-color: #0f172a; border: 1px solid #6366f1; border-radius: 6px; padding: 10px;'>
                        <div style='color: #818cf8; font-weight: bold;'>📝 Đề xuất tạo file mới: <code>{f}</code></div>
                        <div style='margin-top: 6px;'>
                            <a href='createfile:///{quote(f)}' style='background-color: #4f46e5; color: #ffffff; text-decoration: none; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold;'>✅ Tạo File Này</a>
                        </div>
                    </div>
                    """

        if delete_files:
            for df in delete_files:
                f = df['file']
                r = df.get('reason', '')
                cards_html += f"""
                <div style='margin-top: 10px; background-color: #422006; border: 1px solid #eab308; border-radius: 6px; padding: 10px;'>
                    <div style='color: #fde047; font-weight: bold;'>⚠️ Đề xuất xóa file: <code>{f}</code></div>
                    <div style='color: #fef08a; font-size: 11px; margin: 2px 0;'>Lý do: {r}</div>
                    <div style='margin-top: 6px;'>
                        <a href='deletefile:///{quote(f)}' style='background-color: #b91c1c; color: #ffffff; text-decoration: none; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold;'>🗑️ Xác Nhận Xóa</a>
                    </div>
                </div>
                """

        if commands:
            for cmd in commands:
                c = cmd['command']
                desc = cmd.get('description', '')
                if auto_applied:
                    cards_html += f"""
                    <div style='margin-top: 10px; background-color: #082f49; border: 1px solid #0284c7; border-radius: 6px; padding: 10px;'>
                        <div style='color: #38bdf8; font-weight: bold;'>💻 Đang thực thi lệnh Terminal: <code>{c}</code></div>
                        {f"<div style='color: #bae6fd; font-size: 11px; margin: 2px 0;'>Mục đích: {desc}</div>" if desc else ""}
                        <div style='margin-top: 6px;'>
                            <span style='color: #38bdf8; font-size: 11px; font-weight: bold;'>🚀 Đã tự động gửi tới Terminal</span>
                        </div>
                    </div>
                    """
                else:
                    cards_html += f"""
                    <div style='margin-top: 10px; background-color: #082f49; border: 1px solid #0284c7; border-radius: 6px; padding: 10px;'>
                        <div style='color: #38bdf8; font-weight: bold;'>💻 Lệnh Terminal Đề Xuất: <code>{c}</code></div>
                        {f"<div style='color: #bae6fd; font-size: 11px; margin: 2px 0;'>Mục đích: {desc}</div>" if desc else ""}
                        <div style='margin-top: 6px;'>
                            <a href='runcmd:///{quote(c)}' style='background-color: #0284c7; color: #ffffff; text-decoration: none; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold;'>▶️ Chạy Lệnh Trong Terminal</a>
                        </div>
                    </div>
                    """

        token_info = ""
        if tokens:
            inp = tokens.get('input_tokens', 0)
            out = tokens.get('output_tokens', 0)
            token_info = f"<div style='margin-top: 8px; font-size: 11px; color: #64748b;'>📊 Tiêu thụ: Input {inp:,} tok | Output {out:,} tok</div>"

        msg_html = f"""
        <div style='margin-bottom: 20px; display: flex;'>
            <div style='background-color: #0d1322; border: 1px solid #1e293b; border-radius: 8px; padding: 12px 16px; width: 95%;'>
                <div style='font-size: 11px; font-weight: bold; color: #818cf8; margin-bottom: 6px;'>⚡ Graft Agent:</div>
                <div style='font-size: 13px;'>{content_html}</div>
                {cards_html}
                {token_info}
            </div>
        </div>
        """
        self.chat_history.append(msg_html)
        self.render_all()

    def add_system_message(self, title: str, text: str, persist: bool = True):
        msg_dict = {"role": "system", "title": title, "text": text}
        if persist:
            self.raw_messages.append(msg_dict)
            self.message_persisted.emit(msg_dict)

        msg_html = f"""
        <div style='margin-bottom: 16px;'>
            <div style='background-color: #0f172a; border-left: 4px solid #6366f1; border-radius: 6px; padding: 10px 14px;'>
                <div style='font-size: 12px; font-weight: bold; color: #818cf8;'>{title}</div>
                <div style='font-size: 12px; color: #cbd5e1; margin-top: 4px;'>{text}</div>
            </div>
        </div>
        """
        self.chat_history.append(msg_html)
        self.render_all()

    def load_messages(self, messages: List[dict]):
        """Nạp lại danh sách tin nhắn của một cuộc trò chuyện từ đĩa."""
        self.chat_history.clear()
        self.raw_messages.clear()
        for m in messages:
            role = m.get("role")
            if role == "user":
                self.add_user_message(m.get("text", ""), images=m.get("images", []), persist=False)
            elif role == "ai":
                self.add_ai_message(
                    m.get("text", ""),
                    graft_actions=m.get("graft_actions"),
                    create_files=m.get("create_files"),
                    delete_files=m.get("delete_files"),
                    commands=m.get("commands"),
                    tokens=m.get("tokens"),
                    persist=False
                )
            elif role == "system":
                self.add_system_message(m.get("title", ""), m.get("text", ""), persist=False)
        self.raw_messages = list(messages)
        self.render_all()

    def render_all(self):
        full_html = f"""
        <html>
        <head>
            <style>
                body {{ background-color: #070a13; color: #e2e8f0; margin: 0; padding: 0; }}
            </style>
        </head>
        <body>
            {''.join(self.chat_history)}
        </body>
        </html>
        """
        self.browser.setHtml(full_html)
        self.browser.moveCursor(QTextCursor.MoveOperation.End)

    def clear_chat(self):
        self.chat_history.clear()
        self.raw_messages.clear()
        self.render_all()

    def on_link_clicked(self, url):
        scheme = url.scheme().lower()
        path = unquote(url.path().lstrip("/"))
        if scheme == "runcmd":
            self.action_run_command_clicked.emit(path)
        elif scheme == "graftview":
            self.action_view_diff_clicked.emit({"file": path})
        elif scheme == "graftapply":
            self.action_apply_clicked.emit({"file": path})
        elif scheme == "createfile":
            self.action_create_file_clicked.emit(path)
        elif scheme == "deletefile":
            self.action_delete_file_clicked.emit(path)
