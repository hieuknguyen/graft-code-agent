import html
import re
from urllib.parse import quote, unquote
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser, QMessageBox
from PySide6.QtCore import Signal
from PySide6.QtGui import QTextCursor, QTextDocument

from core.text_utils import sanitize_latex

class ChatWidget(QWidget):
    action_apply_clicked = Signal(dict)
    action_view_diff_clicked = Signal(dict)
    action_run_command_clicked = Signal(str)
    action_create_file_clicked = Signal(str)
    action_delete_file_clicked = Signal(str)
    action_open_file_clicked = Signal(str)
    message_persisted = Signal(dict)
    message_deleted = Signal(int)
    messages_cleared = Signal()
    content_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.chat_history: List[str] = []
        self.raw_messages: List[Dict[str, Any]] = []
        self._thinking_html: Optional[str] = None
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
        clean_text = sanitize_latex(text)
        doc = QTextDocument()
        doc.setMarkdown(clean_text)
        body_match = re.search(r"<body[^>]*>(.*)</body>", doc.toHtml(), flags=re.DOTALL)
        body = body_match.group(1).strip() if body_match else html.escape(clean_text).replace("\n", "<br>")
        body = re.sub(r'<p style="', '<p style="color:#c9c9c9; ', body)
        body = re.sub(r'<li style="', '<li style="color:#c9c9c9; ', body)
        body = re.sub(r'<pre style="', '<pre style="background-color:#202020; color:#c9c9c9; ', body)
        body = re.sub(r'<h([1-6]) style="', r'<h\1 style="color:#dddddd; ', body)
        body = body.replace("<code>", "<code style='color:#d0d0d0; background-color:#292929;'>")
        return body

    def _message_spacer(self) -> str:
        return "<p style='font-size:6px; line-height:6px; margin:0;'>&nbsp;</p>"

    def _header_row(self, title: str, msg_idx: int, align: str = "left") -> str:
        color = "#7e828d"
        return f"""
        <table width='100%' cellspacing='0' cellpadding='0' border='0' style='margin-bottom:6px;'>
          <tr>
            <td align='left'><span style='font-size:11px; font-weight:bold; color:#d0d0d0;'>{title}</span></td>
            <td align='right'><a href='deletemsg:///{msg_idx}' style='color:{color}; text-decoration:none; font-size:11px; padding:2px 4px;' title='Xóa đoạn tin nhắn này'>🗑️ Xóa</a></td>
          </tr>
        </table>
        """

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

    def add_user_message(self, text: str, images: Optional[List[str]] = None, persist: bool = True, msg_index: Optional[int] = None, render: bool = True):
        msg_dict = {"role": "user", "text": text, "images": images or []}
        if persist:
            self.raw_messages.append(msg_dict)
            self.message_persisted.emit(msg_dict)

        idx = msg_index if msg_index is not None else (len(self.raw_messages) - 1)
        escaped = html.escape(text).replace("\n", "<br>")
        
        images_html = ""
        if images:
            img_tags = ""
            for img_uri in images:
                img_tags += f"<p style='margin-top:8px;'><img src='{img_uri}' width='320' /></p>"
            images_html = img_tags

        header = self._header_row("BẠN", idx, align="right")
        msg_html = self._bubble(
            f"{header}"
            f"<p style='font-size:13px; color:#dddddd; margin:0;'>{escaped}</p>"
            f"{images_html}",
            "#2d313a",
            "#414855",
            align="right",
        )
        self.chat_history.append(msg_html)
        if render:
            self.render_all()

    def add_ai_message(self, text: str, graft_actions: List[dict] = None, create_files: List[dict] = None,
                       delete_files: List[dict] = None, commands: List[dict] = None, tokens: dict = None, persist: bool = True, auto_applied: bool = False, msg_index: Optional[int] = None, render: bool = True):
        msg_dict = {
            "role": "ai",
            "text": text,
            "graft_actions": graft_actions,
            "create_files": create_files,
            "delete_files": delete_files,
            "commands": commands,
            "tokens": tokens,
            "auto_applied": auto_applied
        }
        if persist:
            self.raw_messages.append(msg_dict)
            self.message_persisted.emit(msg_dict)

        idx = msg_index if msg_index is not None else (len(self.raw_messages) - 1)
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

        header = self._header_row("GRAFT", idx)
        msg_html = self._bubble(
            f"{header}"
            f"<div style='font-size:13px;'>{content_html}</div>"
            f"{cards_html}"
            f"{token_info}",
            "#202126",
            "#292929",
        )
        self.chat_history.append(msg_html)
        if render:
            self.render_all()

    def format_system_text(self, text: str) -> str:
        if not text:
            return ""
        # Check if text already contains standard HTML formatting tags
        has_html = bool(re.search(r"<\s*/?\s*(?:code|br|b|i|a|span|div|p|strong|em|ul|ol|li)\b", text, re.IGNORECASE))
        if has_html:
            formatted = text
            # Ensure <code> tags get clean styling if not already styled
            formatted = re.sub(
                r"<code>(?!\s*<code)",
                "<code style='color:#a8dab5; background-color:#18191d; border:1px solid #333842; padding:1px 5px; border-radius:3px; font-family:Consolas, monospace;'>",
                formatted
            )
            # Ensure <a> tags have link styling if not present
            formatted = re.sub(
                r"<a\s+href=",
                "<a style='color:#818cf8; text-decoration:none; font-weight:bold;' href=",
                formatted
            )
            return formatted
        else:
            escaped = html.escape(text)
            escaped = re.sub(
                r"`([^`]+)`",
                r"<code style='color:#a8dab5; background-color:#18191d; border:1px solid #333842; padding:1px 5px; border-radius:3px; font-family:Consolas, monospace;'>\1</code>",
                escaped
            )
            return escaped.replace("\n", "<br>")

    def add_system_message(self, title: str, text: str, persist: bool = True, msg_index: Optional[int] = None, render: bool = True):
        msg_dict = {"role": "system", "title": title, "text": text}
        if persist:
            self.raw_messages.append(msg_dict)
            self.message_persisted.emit(msg_dict)

        idx = msg_index if msg_index is not None else (len(self.raw_messages) - 1)
        header = self._header_row(title, idx)
        formatted_content = self.format_system_text(text)
        msg_html = self._bubble(
            f"{header}"
            f"<div style='font-size:12px; color:#c9c9c9; line-height:1.5; margin:0;'>{formatted_content}</div>",
            "#202020",
            "#4c4c4c",
        )
        self.chat_history.append(msg_html)
        if render:
            self.render_all()

    def load_messages(self, messages: List[dict]):
        """Nạp lại danh sách tin nhắn của một cuộc trò chuyện từ đĩa."""
        self.chat_history.clear()
        self.raw_messages = list(messages)
        for idx, m in enumerate(messages):
            role = m.get("role")
            if role == "user":
                self.add_user_message(m.get("text", ""), images=m.get("images", []), persist=False, msg_index=idx, render=False)
            elif role == "ai":
                self.add_ai_message(
                    m.get("text", ""),
                    graft_actions=m.get("graft_actions"),
                    create_files=m.get("create_files"),
                    delete_files=m.get("delete_files"),
                    commands=m.get("commands"),
                    tokens=m.get("tokens"),
                    persist=False,
                    auto_applied=m.get("auto_applied", False),
                    msg_index=idx,
                    render=False
                )
            elif role == "system":
                self.add_system_message(m.get("title", ""), m.get("text", ""), persist=False, msg_index=idx, render=False)
        self.render_all()

    def confirm_and_delete_message(self, index: int):
        if not (0 <= index < len(self.raw_messages)):
            return
        reply = QMessageBox.question(
            self,
            "Xác Nhận Xóa Đoạn Đối Thoại",
            "Bạn có chắc muốn xóa đoạn tin nhắn này khỏi cuộc trò chuyện?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_message_at(index)

    def delete_message_at(self, index: int):
        if 0 <= index < len(self.raw_messages):
            del self.raw_messages[index]
            self.load_messages(list(self.raw_messages))
            self.message_deleted.emit(index)

    def show_thinking(self, text: str = "🤖 AI đang phân tích và xử lý yêu cầu..."):
        self._thinking_html = f"""
        <table width='100%' cellspacing='0' cellpadding='0' border='0'>
          <tr>
            <td align='left'>
              <table width='100%' cellspacing='0' cellpadding='10' border='0'
                     style='background-color:#1c1e24; border:1px dashed #3e4451;'>
                <tr>
                  <td>
                    <span style='color:#a8dab5; font-size:13px; font-weight:bold;'>{html.escape(text)}</span>
                    <div style='color:#8c93a0; font-size:11px; margin-top:4px;'>⏳ Đang kết nối mô hình AI & trích xuất ngữ cảnh... Vui lòng đợi trong giây lát.</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
        {self._message_spacer()}
        """
        self.render_all()

    def hide_thinking(self):
        if getattr(self, "_thinking_html", None) is not None:
            self._thinking_html = None
            self.render_all()

    def render_all(self):
        content = ''.join(self.chat_history)
        if getattr(self, "_thinking_html", None):
            content += self._thinking_html
        full_html = f"""
        <html>
        <head>
            <style>
                body {{ background-color: #101010; color: #dedede; margin: 0; padding: 0; }}
                code {{ font-family: "Cascadia Code", "Consolas", "Courier New", monospace; color: #a8dab5; background-color: #18191d; }}
                a {{ color: #818cf8; text-decoration: none; }}
            </style>
        </head>
        <body>
            {content}
        </body>
        </html>
        """
        self.browser.setHtml(full_html)
        self.browser.moveCursor(QTextCursor.MoveOperation.End)
        self.content_changed.emit(bool(self.chat_history or getattr(self, "_thinking_html", None)))

    def clear_chat(self):
        self._thinking_html = None
        self.chat_history.clear()
        self.raw_messages.clear()
        self.render_all()
        self.messages_cleared.emit()

    def on_link_clicked(self, url):
        scheme = url.scheme().lower()
        path = unquote(url.path().lstrip("/"))
        raw_str = url.toString() or url.path()
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
        elif scheme in ("open_file", "openfile"):
            self.action_open_file_clicked.emit(path)
        elif raw_str.startswith(("open_file:", "openfile:")):
            target = unquote(raw_str.split(":", 1)[1].lstrip("/"))
            self.action_open_file_clicked.emit(target)
        elif scheme == "deletemsg":
            try:
                msg_idx = int(path)
                self.confirm_and_delete_message(msg_idx)
            except Exception:
                pass
