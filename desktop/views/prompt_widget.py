import os
import base64
from typing import Optional, List, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPlainTextEdit, QCheckBox, QPushButton, QFrame, QFileDialog,
    QApplication, QScrollArea, QGridLayout, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QBuffer, QIODevice
from PySide6.QtGui import QKeyEvent, QImage, QPixmap
from desktop.icons import icon

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
                background-color: #30323a;
                border: 1px solid #484c57;
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
        lbl_name.setStyleSheet("color: #d5d7de; font-size: 11px;")
        layout.addWidget(lbl_name)

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(18, 18)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #9699a3;
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
    settings_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.attached_images: List[Dict[str, Any]] = []
        self.init_ui()

    def init_ui(self):
        self.setObjectName("promptPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(7)

        context_row = QHBoxLayout()
        context_label = QLabel("Ngữ cảnh")
        context_label.setObjectName("muted")
        context_row.addWidget(context_label)
        self.target_file_combo = QComboBox()
        self.target_file_combo.setMinimumWidth(0)
        self.target_file_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.target_file_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.target_file_combo.setMinimumContentsLength(12)
        self.target_file_combo.addItem("Toàn bộ dự án", "")
        self.target_file_combo.setToolTip("Chọn một tệp hoặc để Agent tìm ngữ cảnh trong dự án")
        context_row.addWidget(self.target_file_combo, 1)
        layout.addLayout(context_row)

        self.preview_container = QWidget()
        self.preview_layout = QHBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_layout.setSpacing(6)
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setWidget(self.preview_container)
        self.preview_scroll.setFixedHeight(64)
        self.preview_scroll.hide()
        layout.addWidget(self.preview_scroll)

        composer = QFrame()
        composer.setObjectName("composer")
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(9, 8, 9, 7)
        composer_layout.setSpacing(4)
        self.prompt_edit = PromptTextEdit(self)
        self.prompt_edit.setObjectName("promptInput")
        self.prompt_edit.setPlaceholderText("Hỏi Agent hoặc mô tả điều bạn muốn xây dựng…")
        self.prompt_edit.setMinimumHeight(82)
        self.prompt_edit.setMaximumHeight(110)
        composer_layout.addWidget(self.prompt_edit)

        tools = QWidget()
        tools.setObjectName("composerTools")
        tools_layout = QHBoxLayout(tools)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(8)
        self.btn_attach = QPushButton(icon("plus"), "")
        self.btn_attach.setObjectName("iconButton")
        self.btn_attach.setFixedSize(28, 28)
        self.btn_attach.setToolTip("Đính kèm ảnh · Có thể dán ảnh bằng Ctrl+V")
        self.btn_attach.setAccessibleName("Đính kèm ảnh")
        self.btn_attach.clicked.connect(self.choose_image_files)
        tools_layout.addWidget(self.btn_attach)
        self.model_button = QPushButton("Model")
        self.model_button.setObjectName("modelButton")
        self.model_button.setMinimumWidth(0)
        self.model_button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.model_button.clicked.connect(self.settings_requested.emit)
        tools_layout.addWidget(self.model_button, 1)
        self.btn_graft = QPushButton(icon("send", "#172338"), "")
        self.btn_graft.setObjectName("primaryButton")
        self.btn_graft.setFixedSize(30, 30)
        self.btn_graft.setToolTip("Gửi yêu cầu (Ctrl+Enter)")
        self.btn_graft.setAccessibleName("Gửi yêu cầu")
        self.btn_graft.clicked.connect(self.submit_prompt)
        tools_layout.addWidget(self.btn_graft)
        composer_layout.addWidget(tools)
        layout.addWidget(composer)

        options_row = QHBoxLayout()
        self.mode_label = QLabel("Xem trước thay đổi")
        self.mode_label.setObjectName("muted")
        options_row.addWidget(self.mode_label)
        options_row.addStretch()
        self.btn_options = QPushButton("Tùy chọn ▾")
        self.btn_options.setObjectName("iconButton")
        self.btn_options.setCheckable(True)
        options_row.addWidget(self.btn_options)
        layout.addLayout(options_row)
        self.options_panel = QWidget()
        self.options_panel.setObjectName("promptOptions")
        options_layout = QGridLayout(self.options_panel)
        options_layout.setContentsMargins(0, 0, 0, 4)
        self.chk_thinking = QCheckBox("Suy nghĩ sâu")
        self.chk_thinking.setChecked(True)
        self.chk_dual = QCheckBox("Dual AI Review")
        self.chk_auto = QCheckBox("Tự động áp dụng")
        self.chk_auto.setToolTip("Cho phép áp dụng các đề xuất mà không nhấn nút Áp dụng")
        self.chk_feedback = QCheckBox("Đọc log và tiếp tục")
        self.chk_feedback.setChecked(True)
        self.chk_auto.toggled.connect(lambda enabled: self.mode_label.setText(
            "Tự động áp dụng" if enabled else "Xem trước thay đổi"
        ))
        for i, checkbox in enumerate((self.chk_thinking, self.chk_dual, self.chk_auto, self.chk_feedback)):
            options_layout.addWidget(checkbox, i // 2, i % 2)
        self.options_panel.hide()
        self.btn_options.toggled.connect(self.options_panel.setVisible)
        self.btn_options.toggled.connect(lambda checked: self.btn_options.setText(
            "Tùy chọn ▴" if checked else "Tùy chọn ▾"
        ))
        layout.addWidget(self.options_panel)

        actions = QHBoxLayout()
        self.btn_undo = QPushButton(icon("undo"), "Hoàn tác")
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self.undo_requested.emit)
        actions.addWidget(self.btn_undo)
        self.btn_apply = QPushButton(icon("check", "#a8dab5"), "Áp dụng")
        self.btn_apply.setObjectName("successButton")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self.apply_requested.emit)
        actions.addWidget(self.btn_apply)
        layout.addLayout(actions)
        stats = QHBoxLayout()
        self.badge_in = QLabel("Input: 0")
        self.badge_out = QLabel("Output: 0")
        self.badge_total = QLabel("0 token")
        for badge in (self.badge_in, self.badge_out, self.badge_total):
            badge.setObjectName("muted")
            stats.addWidget(badge)
        layout.addLayout(stats)

    def set_model(self, model: str):
        self.model_button.setText(model)
        self.model_button.setToolTip(f"{model} · Mở cấu hình AI")

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
            self.preview_scroll.hide()
            self.btn_attach.setToolTip("Đính kèm ảnh · Có thể dán ảnh bằng Ctrl+V")
            return

        self.preview_scroll.show()
        self.btn_attach.setToolTip(f"Đính kèm ảnh ({len(self.attached_images)})")

        for i, img_item in enumerate(self.attached_images):
            thumb = ImageThumbnail(i, img_item["name"], img_item["pixmap"])
            thumb.removed.connect(self.remove_image)
            self.preview_layout.addWidget(thumb)

        self.preview_layout.addStretch()

    def submit_prompt(self):
        if not self.btn_graft.isEnabled():
            return
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
        self.target_file_combo.addItem("Toàn bộ dự án", "")
        for f in sorted(files):
            self.target_file_combo.addItem(f, f)
        if cur:
            idx = self.target_file_combo.findData(cur)
            if idx >= 0:
                self.target_file_combo.setCurrentIndex(idx)

    def set_tokens(self, tokens: dict):
        inp = tokens.get("input_tokens", 0)
        out = tokens.get("output_tokens", 0)
        tot = tokens.get("total_tokens", inp + out)
        self.badge_in.setText(f"Input: {inp:,}")
        self.badge_out.setText(f"Output: {out:,}")
        self.badge_total.setText(f"{tot:,} token")
