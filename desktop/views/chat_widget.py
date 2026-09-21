import html
import re
from urllib.parse import quote, unquote
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser
from PySide6.QtCore import Signal
from PySide6.QtGui import QTextCursor, QTextDocument

class ChatWidget(QWidget):
    action_apply_clicked = Signal(dict)
    action_view_diff_clicked = Signal(dict)
    action_run_command_clicked = Signal(str)
    action_create_file_clicked = Signal(str)
    action_delete_file_clicked = Signal(str)
    message_persisted = Signal(dict)
    content_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.chat_history: List[str] = []
        self.raw_messages: List[Dict[str, Any]] = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.browser = QTextBrowser()
        self.browser.setObjectName("chatBrowser")
        self.browser.setOpenExternalLinks(False)
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self.on_link_clicked)
        layout.addWidget(self.browser)
        self.render_all()

    def markdown_to_html(self, text: str) -> str:
        doc = QTextDocument()
        doc.setMarkdown(text)
        body_match = re.search(r"<body[^>]*>(.*)</body>", doc.toHtml(), flags=re.DOTALL)
        body = body_match.group(1).strip() if body_match else html.escape(text).replace("\n", "<br>")
        body = re.sub(r'<p style="', '<p style="color:#c9c9c9; ', body)
        body = re.sub(r'<li style="', '<li style="color:#c9c9c9; ', body)
        body = re.sub(r'<pre style="', '<pre style="background-color:#202020; color:#c9c9c9; ', body)
        body = re.sub(r'<h([1-6]) style="', r'<h\1 style="color:#dddddd; ', body)
        body = body.replace("<code>", "<code style='color:#d0d0d0; background-color:#292929;'>")
        return body

    def _message_spacer(self) -> str:
        return "<p style='font-size:6px; line-height:6px; margin:0;'>&nbsp;</p>"

    def _bubble(self, inner_html: str, bg: str, border: str = "#292929", align: str = "left") -> str:
        width = "86%" if align == "right" else "100%"
        align_attr = "right" if align == "right" else "left"
        return f"""
        <table width='100%' cellspacing='0' cellpadding='0' border='0'>
          <tr>
            <td align='{align_attr}'>
              <table width='{width}' cellspacing='0' cellpadding='12' border='0'
                     style='background-color:{bg}; border:1px solid {border};'>
                <tr><td>{inner_html}</td></tr>
              </table>
            </td>
          </tr>
        </table>
        {self._message_spacer()}
        """

    def add_user_message(self, text: str, images: Optional[List[str]] = None, persist: bool = True):
        msg_dict = {"role": "user", "text": text, "images": images or []}
        if persist:
            self.raw_messages.append(msg_dict)
            self.message_persisted.emit(msg_dict)

        escaped = html.escape(text).replace("\n", "<br>")
        
        images_html = ""
        if images:
            img_tags = ""
            for img_uri in images:
                img_tags += f"<p style='margin-top:8px;'><img src='{img_uri}' width='320' /></p>"
            images_html = img_tags

        msg_html = self._bubble(
            "<p style='font-size:11px; font-weight:bold; color:#d0d0d0; margin:0 0 8px 0;'>BẠN</p>"
            f"<p style='font-size:13px; color:#dddddd; margin:0;'>{escaped}</p>"
            f"{images_html}",
            "#2d313a",
            "#414855",
            align="right",
        )
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
                        <div style='margin-top: 10px; background-color: #202020; border: 1px solid #22c55e; border-radius: 6px; padding: 10px;'>
                            <div style='color: #a8dab5; font-weight: bold;'>💾 Đã tự động cấy ghép AST vào: <code>{f}</code></div>
                            <div style='color: #9699a3; font-size: 11px; margin: 4px 0;'>{act.get('msg', '')}</div>
                            <div style='margin-top: 6px;'>
                                <a href='graftview:///{quote(f)}' style='background-color: #292929; color: #d0d0d0; text-decoration: none; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold; margin-right: 8px;'>🔍 Xem Diff Chi Tiết</a>
                                <span style='color: #22c55e; font-size: 11px; font-weight: bold;'>✅ Đã lưu trực tiếp vào file</span>
                            </div>
                        </div>
                        """
                    else:
                        cards_html += f"""
                        <div style='margin-top: 10px; background-color: #202020; border: 1px solid #22c55e; border-radius: 6px; padding: 10px;'>
                            <div style='color: #a8dab5; font-weight: bold;'>⚡ Đã chuẩn bị cấy ghép AST vào: <code>{f}</code></div>
                            <div style='color: #9699a3; font-size: 11px; margin: 4px 0;'>{act.get('msg', '')}</div>
                            <div style='margin-top: 6px;'>
                                <a href='graftview:///{quote(f)}' style='background-color: #292929; color: #d0d0d0; text-decoration: none; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold; margin-right: 8px;'>🔍 Xem Diff Chi Tiết</a>
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
                    <div style='margin-top: 10px; background-color: #202020; border: 1px solid #4c4c4c; border-radius: 6px; padding: 10px;'>
                        <div style='color: #d0d0d0; font-weight: bold;'>📝 Đã tự động tạo file: <code>{f}</code></div>
                        <div style='margin-top: 6px;'>
                            <a href='open_file:{quote(f)}' style='background-color: #465d80; color: #ffffff; text-decoration: none; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold;'>📄 Mở xem file</a>
                            <span style='color: #22c55e; font-size: 11px; font-weight: bold; margin-left: 8px;'>✅ Đã tạo thành công</span>
                        </div>
                    </div>
                    """
                else:
                    cards_html += f"""
                    <div style='margin-top: 10px; background-color: #202020; border: 1px solid #4c4c4c; border-radius: 6px; padding: 10px;'>
                        <div style='color: #d0d0d0; font-weight: bold;'>📝 Đề xuất tạo file mới: <code>{f}</code></div>
                        <div style='margin-top: 6px;'>
                            <a href='createfile:///{quote(f)}' style='background-color: #465d80; color: #ffffff; text-decoration: none; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold;'>✅ Tạo File Này</a>
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
                    <div style='margin-top: 10px; background-color: #252e3b; border: 1px solid #476080; border-radius: 6px; padding: 10px;'>
                        <div style='color: #d0d0d0; font-weight: bold;'>💻 Đang thực thi lệnh Terminal: <code>{c}</code></div>
                        {f"<div style='color: #b9c9df; font-size: 11px; margin: 2px 0;'>Mục đích: {desc}</div>" if desc else ""}
                        <div style='margin-top: 6px;'>
                            <span style='color: #d0d0d0; font-size: 11px; font-weight: bold;'>🚀 Đã tự động gửi tới Terminal</span>
                        </div>
                    </div>
                    """
                else:
                    cards_html += f"""
                    <div style='margin-top: 10px; background-color: #252e3b; border: 1px solid #476080; border-radius: 6px; padding: 10px;'>
                        <div style='color: #d0d0d0; font-weight: bold;'>💻 Lệnh Terminal Đề Xuất: <code>{c}</code></div>
                        {f"<div style='color: #b9c9df; font-size: 11px; margin: 2px 0;'>Mục đích: {desc}</div>" if desc else ""}
                        <div style='margin-top: 6px;'>
                            <a href='runcmd:///{quote(c)}' style='background-color: #476080; color: #ffffff; text-decoration: none; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold;'>▶️ Chạy Lệnh Trong Terminal</a>
                        </div>
                    </div>
                    """

        token_info = ""
        if tokens:
            inp = tokens.get('input_tokens', 0)
            out = tokens.get('output_tokens', 0)
            token_info = f"<div style='margin-top: 8px; font-size: 11px; color: #9699a3;'>📊 Tiêu thụ: Input {inp:,} tok | Output {out:,} tok</div>"

        msg_html = self._bubble(
            "<p style='font-size:11px; font-weight:bold; color:#d0d0d0; margin:0 0 8px 0;'>GRAFT</p>"
            f"<div style='font-size:13px;'>{content_html}</div>"
            f"{cards_html}"
            f"{token_info}",
            "#202126",
            "#292929",
        )
        self.chat_history.append(msg_html)
        self.render_all()

    def add_system_message(self, title: str, text: str, persist: bool = True):
        msg_dict = {"role": "system", "title": title, "text": text}
        if persist:
            self.raw_messages.append(msg_dict)
            self.message_persisted.emit(msg_dict)

        msg_html = self._bubble(
            f"<p style='font-size:12px; font-weight:bold; color:#d0d0d0; margin:0 0 6px 0;'>{html.escape(title)}</p>"
            f"<p style='font-size:12px; color:#c9c9c9; margin:0;'>{html.escape(text)}</p>",
            "#202020",
            "#4c4c4c",
        )
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
        content = ''.join(self.chat_history)
        full_html = f"""
        <html>
        <head>
            <style>
                body {{ background-color: #101010; color: #dedede; margin: 0; padding: 0; }}
            </style>
        </head>
        <body>
            {content}
        </body>
        </html>
        """
        self.browser.setHtml(full_html)
        self.browser.moveCursor(QTextCursor.MoveOperation.End)
        self.content_changed.emit(bool(self.chat_history))

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
