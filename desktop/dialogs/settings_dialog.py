from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config import AppConfig, GATEWAY_PROVIDER, GEMINI_PROVIDER, save_config


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Cấu Hình Nhà Cung Cấp AI")
        self.resize(530, 380)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        self.provider_combo = QComboBox()
        self.provider_combo.addItem("Gemini trực tiếp (khuyến nghị)", GEMINI_PROVIDER)
        self.provider_combo.addItem("AI Gateway cũ", GATEWAY_PROVIDER)
        provider_index = self.provider_combo.findData(self.config.provider)
        self.provider_combo.setCurrentIndex(max(provider_index, 0))
        form.addRow(QLabel("Nhà cung cấp:"), self.provider_combo)

        self.gemini_hint = QLabel(
            "Gemini trực tiếp đọc GEMINI_API_KEY từ biến môi trường. "
            "Khóa không được hiển thị hoặc lưu trong ứng dụng/config.yaml."
        )
        self.gemini_hint.setWordWrap(True)
        form.addRow(self.gemini_hint)

        self.gateway_fields = QWidget()
        gateway_form = QFormLayout(self.gateway_fields)
        gateway_form.setContentsMargins(0, 0, 0, 0)
        gateway_form.setSpacing(10)

        self.url_edit = QLineEdit(self.config.gateway_url)
        self.url_edit.setPlaceholderText("http://localhost:5678/webhook/antigravity-chat")
        gateway_form.addRow(QLabel("Gateway URL:"), self.url_edit)

        # This field represents only a legacy gateway key. Do not use or show
        # config.gemini_api_key anywhere in this dialog.
        self.key_edit = QLineEdit(
            self.config.api_key if self.config.provider == GATEWAY_PROVIDER else ""
        )
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("Legacy gateway API key")
        gateway_form.addRow(QLabel("Gateway API Key:"), self.key_edit)
        form.addRow(self.gateway_fields)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        models = [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
            "gemini-3.8-flash-tiered",
            "gemini-3.8-flash-thinking-tiered",
            "claude-sonnet-4-6",
            "claude-opus-4-6",
            "gpt-4.5",
        ]
        self.model_combo.addItems(models)
        self.model_combo.setCurrentText(self.config.model)
        form.addRow(QLabel("AI Model Chính:"), self.model_combo)

        self.eval_combo = QComboBox()
        self.eval_combo.setEditable(True)
        self.eval_combo.addItems(models)
        self.eval_combo.setCurrentText(self.config.evaluator_model)
        form.addRow(QLabel("AI Model Phản Biện (Dual):"), self.eval_combo)

        self.chk_web_search = QCheckBox("Tự động tìm kiếm web khi cần (AI tự quyết định)")
        self.chk_web_search.setChecked(getattr(self.config, "web_search", True))
        self.chk_web_search.setToolTip("Khi bật, AI sẽ tự động phân tích câu hỏi và tra cứu Internet khi cần thiết mà bạn không phải bật thủ công.")
        form.addRow(QLabel("Tìm kiếm mạng:"), self.chk_web_search)

        self.spin_max_loops = QSpinBox()
        self.spin_max_loops.setRange(0, 9999)
        self.spin_max_loops.setValue(getattr(self.config, "max_feedback_loops", 0))
        self.spin_max_loops.setSpecialValueText("Không giới hạn (0)")
        self.spin_max_loops.setToolTip("Số bước chạy lệnh terminal và phân tích log tự động tối đa. Đặt 0 để AI được phép chạy bao nhiêu lệnh cũng được.")
        form.addRow(QLabel("Giới hạn bước chạy lệnh:"), self.spin_max_loops)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Hủy")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton("Lưu Cấu Hình")
        btn_save.setObjectName("primaryButton")
        btn_save.clicked.connect(self.save_settings)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)
        self.provider_combo.currentIndexChanged.connect(self._update_provider_controls)
        self._update_provider_controls()

    def _selected_provider(self) -> str:
        return self.provider_combo.currentData() or GEMINI_PROVIDER

    def _update_provider_controls(self):
        using_gateway = self._selected_provider() == GATEWAY_PROVIDER
        self.gateway_fields.setVisible(using_gateway)
        self.gemini_hint.setVisible(not using_gateway)

    def save_settings(self):
        provider = self._selected_provider()
        model = self.model_combo.currentText().strip()
        eval_model = self.eval_combo.currentText().strip()

        if not model:
            QMessageBox.warning(self, "Lỗi", "Vui lòng nhập AI Model Chính")
            return

        if provider == GATEWAY_PROVIDER:
            url = self.url_edit.text().strip()
            if not url:
                QMessageBox.warning(self, "Lỗi", "Vui lòng nhập Gateway URL")
                return
            self.config.gateway_url = url
            self.config.api_key = self.key_edit.text().strip()
        else:
            # Prevent a gateway credential inherited from an earlier config from
            # being retained in a direct-Gemini save. The actual Gemini key is
            # left untouched in memory and is never serialized by save_config.
            self.config.api_key = ""

        self.config.provider = provider
        self.config.model = model
        self.config.evaluator_model = eval_model
        self.config.web_search = self.chk_web_search.isChecked()
        self.config.max_feedback_loops = self.spin_max_loops.value()

        save_config(self.config)
        if provider == GEMINI_PROVIDER:
            QMessageBox.information(
                self,
                "Thành Công",
                "Đã lưu cấu hình Gemini. GEMINI_API_KEY vẫn chỉ được đọc từ biến môi trường.",
            )
        else:
            QMessageBox.information(self, "Thành Công", "Đã lưu cấu hình Gateway.")
        self.accept()
