import os
import base64
from typing import Optional, List, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPlainTextEdit, QCheckBox, QPushButton, QFrame, QFileDialog,
    QApplication, QScrollArea
)
from PySide6.QtCore import Qt, Signal, QBuffer, QIODevice
from PySide6.QtGui import QKeyEvent, QImage, QPixmap

def qimage_to_data_uri(img: QImage) -> str:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    b64 = base64.b64encode(buf.data().data()).decode('ascii')
    return f"data:image/png;base64,{b64}"

def file_to_data_uri(filepath: str) -> str:
    ext = os.path.splitext(filepath)[1].lower().replace('.', '')
    mime_map = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
        "bmp": "image/bmp"
    }
    mime = mime_map.get(ext, "image/png")
    with open(filepath, "rb") as f:
        b64 = base64.b64encode(f.read()).decode('ascii')
    return f"data:{mime};base64,{b64}"

class ImageThumbnail(QFrame):
    removed = Signal(int)

    def __init__(self, index: int, name: str, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.index = index
        self.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border: 1px solid #475569;
                border-radius: 6px;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        lbl_img = QLabel()
        scaled = pixmap.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        lbl_img.setPixmap(scaled)
        layout.addWidget(lbl_img)

        display_name = name if len(name) <= 18 else (name[:15] + "...")
        lbl_name = QLabel(display_name)
        lbl_name.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        layout.addWidget(lbl_name)

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(18, 18)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #94a3b8;
                border: none;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #ef4444;
            }
        """)
        btn_del.clicked.connect(lambda: self.removed.emit(self.index))
        layout.addWidget(btn_del)

class PromptTextEdit(QPlainTextEdit):
    def __init__(self, prompt_widget, parent=None):
        super().__init__(parent)
        self.prompt_widget = prompt_widget
        self.setAcceptDrops(True)

    def keyPressEvent(self, event: QKeyEvent):
        # Dán ảnh từ Clipboard (Ctrl + V)
        if event.key() == Qt.Key.Key_V and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            clipboard = QApplication.clipboard()
            mime = clipboard.mimeData()
            if mime.hasImage():
                img = clipboard.image()
                if not img.isNull():
                    self.prompt_widget.add_qimage(img, name=f"screenshot_{len(self.prompt_widget.attached_images) + 1}.png")
                    return
        # Gửi prompt (Ctrl + Enter)
        if event.key() == Qt.Key.Key_Return and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.prompt_widget.submit_prompt()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                fpath = url.toLocalFile()
                if fpath.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif')):
                    self.prompt_widget.add_image_file(fpath)
            event.acceptProposedAction()
            return
        elif event.mimeData().hasImage():
            img = event.mimeData().imageData()
            if img:
                self.prompt_widget.add_qimage(img, name=f"dragged_{len(self.prompt_widget.attached_images) + 1}.png")
                event.acceptProposedAction()
                return
        super().dropEvent(event)

class PromptWidget(QWidget):
    graft_requested = Signal(str, str, dict) # task, target_file, options
    apply_requested = Signal()
    undo_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.attached_images: List[Dict[str, Any]] = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(6)

        # Top line: Target file selector & Tokens Stat Badges
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("🎯 Tệp Mục Tiêu:"))

        self.target_file_combo = QComboBox()
        self.target_file_combo.setMinimumWidth(240)
        self.target_file_combo.addItem("(AI tự động phát hiện)", "")
        top_bar.addWidget(self.target_file_combo)
        top_bar.addStretch()

        # Token stats badges
        self.badge_in = QLabel("Input: 0 tok")
        self.badge_in.setStyleSheet("background-color: rgba(99, 102, 241, 0.2); color: #818cf8; border: 1px solid #4f46e5; border-radius: 4px; padding: 2px 6px; font-size: 11px;")
        top_bar.addWidget(self.badge_in)

        self.badge_out = QLabel("Output: 0 tok")
        self.badge_out.setStyleSheet("background-color: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #059669; border-radius: 4px; padding: 2px 6px; font-size: 11px;")
        top_bar.addWidget(self.badge_out)

        self.badge_total = QLabel("Tổng: 0 tok")
        self.badge_total.setStyleSheet("background-color: rgba(148, 163, 184, 0.2); color: #cbd5e1; border: 1px solid #475569; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: bold;")
        top_bar.addWidget(self.badge_total)

        layout.addLayout(top_bar)

        # Thanh xem trước hình ảnh đính kèm (Image Preview Strip)
        self.preview_container = QWidget()
        self.preview_layout = QHBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_layout.setSpacing(8)
        self.preview_layout.addStretch()
        self.preview_container.setVisible(False)
        layout.addWidget(self.preview_container)

        # Prompt input text edit với hỗ trợ Paste ảnh & Drag-drop
        self.prompt_edit = PromptTextEdit(self)
        self.prompt_edit.setPlaceholderText("Nhập yêu cầu lập trình hoặc dán ảnh chụp màn hình (Ctrl + V)...\nPhím tắt: Nhấn Ctrl + Enter để gửi cấy ghép.")
        self.prompt_edit.setMaximumHeight(90)
        layout.addWidget(self.prompt_edit)

        # Bottom Action Bar
        bottom_bar = QHBoxLayout()

        # Options Checkboxes
        self.chk_thinking = QCheckBox("Thinking Mode")
        self.chk_thinking.setChecked(True)
        self.chk_thinking.setToolTip("Cho phép AI suy nghĩ logic sâu trước khi cấy ghép")
        bottom_bar.addWidget(self.chk_thinking)

        self.chk_dual = QCheckBox("Dual AI Review")
        self.chk_dual.setToolTip("Dùng thêm AI phản biện chéo để đảm bảo chất lượng code tối đa")
        bottom_bar.addWidget(self.chk_dual)

        self.chk_auto = QCheckBox("Tự động Áp dụng (Auto-Execute)")
        self.chk_auto.setChecked(True)
        self.chk_auto.setStyleSheet("color: #4ade80; font-weight: bold;")
        self.chk_auto.setToolTip("Tự động tạo file, sửa code và thực thi ngay lập tức mà không cần nhấn xác nhận")
        bottom_bar.addWidget(self.chk_auto)

        self.chk_feedback = QCheckBox("Tự Động Đọc Log & Chạy Tiếp (Loop)")
        self.chk_feedback.setChecked(True)
        self.chk_feedback.setStyleSheet("color: #38bdf8; font-weight: bold;")
        self.chk_feedback.setToolTip("AI tự động đọc log kết quả từ Terminal và gửi tiếp các lệnh cần thiết cho đến khi hoàn tất")
        bottom_bar.addWidget(self.chk_feedback)

        bottom_bar.addStretch()

        # Nút Đính Kèm Ảnh
        self.btn_attach = QPushButton("🖼️ Thêm Ảnh")
        self.btn_attach.setToolTip("Đính kèm hình ảnh (PNG, JPG, WebP) hoặc có thể dán trực tiếp ảnh chụp màn hình bằng Ctrl + V vào ô nhập")
        self.btn_attach.setStyleSheet("color: #a5b4fc; border-color: #4f46e5; font-size: 11px;")
        self.btn_attach.clicked.connect(self.choose_image_files)
        bottom_bar.addWidget(self.btn_attach)

        # Action Buttons
        self.btn_undo = QPushButton("↩️ Hoàn Tác (Undo)")
        self.btn_undo.setObjectName("undoButton")
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self.undo_requested.emit)
        bottom_bar.addWidget(self.btn_undo)

        self.btn_apply = QPushButton("💾 Áp Dụng (Apply)")
        self.btn_apply.setObjectName("successButton")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self.apply_requested.emit)
        bottom_bar.addWidget(self.btn_apply)

        self.btn_graft = QPushButton("⚡ Gửi Yêu Cầu (Send / Graft)")
        self.btn_graft.setObjectName("primaryButton")
        self.btn_graft.setStyleSheet("padding: 8px 18px; font-weight: bold;")
        self.btn_graft.clicked.connect(self.submit_prompt)
        bottom_bar.addWidget(self.btn_graft)

        layout.addLayout(bottom_bar)

    def choose_image_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn Hình Ảnh Đính Kèm Cho AI",
            "",
            "Hình Ảnh (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;Tất cả tệp (*.*)"
        )
        for f in files:
            self.add_image_file(f)

    def add_image_file(self, filepath: str):
        try:
            data_uri = file_to_data_uri(filepath)
            pixmap = QPixmap(filepath)
            name = os.path.basename(filepath)
            self.attached_images.append({
                "data_uri": data_uri,
                "name": name,
                "pixmap": pixmap
            })
            self.render_image_previews()
        except Exception as e:
            print("Lỗi đính kèm file ảnh:", e)

    def add_qimage(self, qimg: QImage, name: str = "screenshot.png"):
        try:
            data_uri = qimage_to_data_uri(qimg)
            pixmap = QPixmap.fromImage(qimg)
            self.attached_images.append({
                "data_uri": data_uri,
                "name": name,
                "pixmap": pixmap
            })
            self.render_image_previews()
        except Exception as e:
            print("Lỗi đính kèm QImage:", e)

    def remove_image(self, index: int):
        if 0 <= index < len(self.attached_images):
            self.attached_images.pop(index)
            self.render_image_previews()

    def clear_images(self):
        self.attached_images.clear()
        self.render_image_previews()

    def render_image_previews(self):
        # Xóa các widget cũ trong preview layout
        while self.preview_layout.count() > 0:
            item = self.preview_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not self.attached_images:
            self.preview_container.setVisible(False)
            self.btn_attach.setText("🖼️ Thêm Ảnh")
            return

        self.preview_container.setVisible(True)
        self.btn_attach.setText(f"🖼️ Ảnh ({len(self.attached_images)})")

        lbl_title = QLabel(f"📸 {len(self.attached_images)} ảnh đính kèm:")
        lbl_title.setStyleSheet("color: #818cf8; font-size: 11px; font-weight: bold;")
        self.preview_layout.addWidget(lbl_title)

        for i, img_item in enumerate(self.attached_images):
            thumb = ImageThumbnail(i, img_item["name"], img_item["pixmap"])
            thumb.removed.connect(self.remove_image)
            self.preview_layout.addWidget(thumb)

        self.preview_layout.addStretch()

    def submit_prompt(self):
        task = self.prompt_edit.toPlainText().strip()
        images = [item["data_uri"] for item in self.attached_images]

        if not task and not images:
            return

        if not task and images:
            task = "Hãy quan sát và phân tích hình ảnh đính kèm trên để thực hiện yêu cầu hoặc giải thích các vấn đề trong ảnh."

        target_file = self.target_file_combo.currentData()
        options = {
            "thinking": self.chk_thinking.isChecked(),
            "dual_ai": self.chk_dual.isChecked(),
            "auto_apply": self.chk_auto.isChecked(),
            "images": images
        }
        self.prompt_edit.clear()
        self.clear_images()
        self.graft_requested.emit(task, target_file, options)

    def update_file_list(self, files: List[str]):
        cur = self.target_file_combo.currentData()
        self.target_file_combo.clear()
        self.target_file_combo.addItem("(AI tự động phát hiện)", "")
        for f in sorted(files):
            self.target_file_combo.addItem(f"📄 {f}", f)
        if cur:
            idx = self.target_file_combo.findData(cur)
            if idx >= 0:
                self.target_file_combo.setCurrentIndex(idx)

    def set_tokens(self, tokens: dict):
        inp = tokens.get("input_tokens", 0)
        out = tokens.get("output_tokens", 0)
        tot = tokens.get("total_tokens", inp + out)
        self.badge_in.setText(f"Input: {inp:,} tok")
        self.badge_out.setText(f"Output: {out:,} tok")
        self.badge_total.setText(f"Tổng: {tot:,} tok")
