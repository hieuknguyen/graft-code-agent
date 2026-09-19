import os
import re
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QMessageBox, QStatusBar, QFileDialog, QMenuBar, QMenu,
    QLabel, QPushButton, QFrame, QButtonGroup
)
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QAction

from config import load_config, save_config, AppConfig
from core.agent import GraftAgent
from core.process_runner import ProcessRunner
from core.session_manager import SessionManager
from desktop.theme import DARK_STYLESHEET
from desktop.icons import icon
from desktop.views.sidebar_widget import SidebarWidget
from desktop.views.editor_widget import EditorWidget
from desktop.views.prompt_widget import PromptWidget
from desktop.dialogs.settings_dialog import SettingsDialog
from desktop.threads import ScanWorker, GraftWorker, ApplyWorker, UndoWorker, AgentFeedbackWorker, DoctorWorker, ServerHealthProbeWorker

class MainWindow(QMainWindow):
    def __init__(self, initial_dir: str = None):
        super().__init__()
        self.setWindowTitle("Graft Code Agent")
        self.setMinimumSize(1000, 660)
        self.resize(1360, 840)
        self.setStyleSheet(DARK_STYLESHEET)

        self.config: AppConfig = load_config()
        self.root_dir = os.path.abspath(initial_dir or os.environ.get("GRAFT_ROOT_DIR") or os.getcwd())
        self.session_mgr = SessionManager()
        self.current_project = self.session_mgr.get_or_create_project(self.root_dir)
        self.current_conv_id: Optional[str] = None
        self.agent = GraftAgent(self.config, self.root_dir)
        self.scan_worker = None
        self._pending_scan_welcome = None
        self.last_actions = []
        self.pending_creates = []
        self.feedback_loop_active = False
        self.feedback_loop_count = 0
        self.max_feedback_loops = 6
        self.loop_goal = ""

        self.process_runner = ProcessRunner(self)
        self.process_runner.output_received.connect(self.on_process_output)
        self.process_runner.process_started.connect(self.on_process_started)
        self.process_runner.process_finished.connect(self.on_process_finished)
        self.process_runner.command_completed.connect(self.on_command_completed)
        self.process_runner.server_detected.connect(self.on_server_detected)

        self.init_ui()
        self.init_menu()
        self.init_status_bar()

        QTimer.singleShot(200, self.initial_setup)

    def init_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("workbench")
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        command_bar = QFrame()
        command_bar.setObjectName("commandBar")
        command_bar.setFixedHeight(42)
        bar_layout = QHBoxLayout(command_bar)
        bar_layout.setContentsMargins(15, 5, 12, 5)
        mark = QLabel()
        mark.setPixmap(icon("spark", "#aecbfa", 21).pixmap(21, 21))
        bar_layout.addWidget(mark)
        brand = QLabel("Graft")
        brand.setObjectName("brand")
        bar_layout.addWidget(brand)
        bar_layout.addStretch()
        self.workspace_button = QPushButton(icon("search"), "")
        self.workspace_button.setObjectName("commandSearch")
        self.workspace_button.setMinimumWidth(260)
        self.workspace_button.setMaximumWidth(480)
        self.workspace_button.clicked.connect(self.focus_file_search)
        bar_layout.addWidget(self.workspace_button, 3)
        bar_layout.addStretch()
        self.agent_toggle = QPushButton(icon("panel"), "Agent")
        self.agent_toggle.setToolTip("Hiện / ẩn khung Agent (Ctrl+Alt+A)")
        self.agent_toggle.clicked.connect(self.toggle_agent)
        bar_layout.addWidget(self.agent_toggle)
        main_layout.addWidget(command_bar)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        rail = QWidget()
        rail.setObjectName("activityBar")
        rail.setFixedWidth(48)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(0, 5, 0, 6)
        rail_layout.setSpacing(4)
        self.navigation = QButtonGroup(self)
        self.navigation.setExclusive(True)
        self.activity_buttons = {}
        for name, label, index in (("files", "Explorer", 1), ("chat", "Lịch sử trò chuyện", 0)):
            button = QPushButton(icon(name), "")
            button.setObjectName("activityButton")
            button.setFixedSize(47, 42)
            button.setCheckable(True)
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.clicked.connect(lambda checked=False, tab=index: self.show_sidebar_tab(tab))
            self.navigation.addButton(button, index)
            self.activity_buttons[index] = button
            rail_layout.addWidget(button)
        for name, label, callback in (
            ("search", "Tìm tệp (Ctrl+P)", self.focus_file_search),
            ("terminal", "Terminal (Ctrl+J)", self.toggle_terminal),
        ):
            button = QPushButton(icon(name), "")
            button.setObjectName("activityButton")
            button.setFixedSize(47, 42)
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.clicked.connect(callback)
            rail_layout.addWidget(button)
        rail_layout.addStretch()
        settings_button = QPushButton(icon("settings"), "")
        settings_button.setObjectName("activityButton")
        settings_button.setFixedSize(47, 42)
        settings_button.setToolTip("Cài đặt AI")
        settings_button.setAccessibleName("Cài đặt AI")
        settings_button.clicked.connect(self.open_settings)
        rail_layout.addWidget(settings_button)
        body.addWidget(rail)
        self.h_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.h_splitter.setChildrenCollapsible(False)
        self.h_splitter.setHandleWidth(1)
        self.sidebar = SidebarWidget(self.agent, self.session_mgr, self)
        self.sidebar.project_switched.connect(self.switch_workspace)
        self.sidebar.conversation_selected.connect(self.on_conversation_selected)
        self.sidebar.new_conversation_requested.connect(self.on_new_conversation_requested)
        self.sidebar.rename_conversation_requested.connect(self.on_rename_conversation_requested)
        self.sidebar.delete_conversation_requested.connect(self.on_delete_conversation_requested)
        self.sidebar.file_selected.connect(self.on_file_selected)
        self.sidebar.symbol_selected.connect(self.on_symbol_selected)
        self.sidebar.rescan_requested.connect(lambda: self.do_scan(welcome=False))
        self.sidebar.doctor_requested.connect(self.run_doctor)
        self.sidebar.tabs.currentChanged.connect(self.sync_navigation)
        self.h_splitter.addWidget(self.sidebar)
        self.editor = EditorWidget(self)
        self.editor.chat_view.action_apply_clicked.connect(self.on_chat_apply_clicked)
        self.editor.chat_view.action_view_diff_clicked.connect(self.on_chat_view_diff_clicked)
        self.editor.chat_view.action_run_command_clicked.connect(self.run_terminal_command)
        self.editor.chat_view.action_create_file_clicked.connect(self.create_file_requested)
        self.editor.chat_view.action_delete_file_clicked.connect(self.delete_file_requested)
        self.editor.chat_view.message_persisted.connect(self.on_message_persisted)

        self.editor.terminal_view.run_requested.connect(self.run_terminal_command)
        self.editor.terminal_view.kill_requested.connect(self.on_stop_process_requested)
        self.editor.terminal_view.stdin_requested.connect(self.process_runner.write_stdin)

        self.prompt = PromptWidget(self)
        self.prompt.graft_requested.connect(self.on_graft_requested)
        self.prompt.apply_requested.connect(self.on_apply_requested)
        self.prompt.undo_requested.connect(self.on_undo_requested)
        self.prompt.settings_requested.connect(self.open_settings)
        self.prompt.set_model(self.config.model)
        self.prompt.chk_thinking.setChecked(self.config.thinking)
        self.prompt.chk_dual.setChecked(self.config.dual_ai_mode)
        self.prompt.chk_auto.setChecked(self.config.auto_apply)
        self.editor.set_prompt(self.prompt)
        self.editor.open_folder_requested.connect(self.sidebar.browse_folder)
        self.editor.search_requested.connect(self.focus_file_search)
        self.editor.focus_agent_requested.connect(self.focus_agent)
        self.editor.new_conversation_requested.connect(self.on_new_conversation_requested)
        self.editor.history_requested.connect(lambda: self.show_sidebar_tab(0))
        self.h_splitter.addWidget(self.editor)
        self.h_splitter.setSizes([245, 1067])
        self.h_splitter.setStretchFactor(0, 0)
        self.h_splitter.setStretchFactor(1, 1)
        body.addWidget(self.h_splitter, 1)
        main_layout.addLayout(body, 1)
        self.setCentralWidget(central_widget)
        self.sync_navigation(1)
        self.update_workspace_header()

    def sync_navigation(self, index):
        self.activity_buttons[index].setChecked(True)

    def show_sidebar_tab(self, index):
        self.sidebar.show()
        self.sidebar.tabs.setCurrentIndex(index)
        self.sync_navigation(index)

    def focus_file_search(self):
        self.show_sidebar_tab(1)
        self.sidebar.file_search.setFocus()
        self.sidebar.file_search.selectAll()

    def focus_agent(self):
        self.editor.show_chat()
        self.prompt.prompt_edit.setFocus()

    def toggle_agent(self):
        self.editor.agent_panel.setVisible(not self.editor.agent_panel.isVisible())

    def toggle_terminal(self):
        self.editor.terminal_view.setVisible(not self.editor.terminal_view.isVisible())

    def update_workspace_header(self):
        name = self.current_project["name"]
        self.workspace_button.setText(f"{name}     ·     Ctrl+P")
        self.workspace_button.setToolTip(self.root_dir)
        self.setWindowTitle(f"{name} — Graft")

    def init_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")

        act_import = QAction(icon("folder"), "Mở thư mục dự án…", self)
        act_import.setShortcut("Ctrl+O")
        act_import.triggered.connect(self.sidebar.browse_folder)
        file_menu.addAction(act_import)

        act_rescan = QAction(icon("refresh"), "Quét lại codebase", self)
        act_rescan.setShortcut("F5")
        act_rescan.triggered.connect(lambda: self.do_scan(welcome=False))
        file_menu.addAction(act_rescan)

        act_doctor = QAction(icon("activity"), "Kiểm tra môi trường…", self)
        act_doctor.setShortcut("F6")
        act_doctor.triggered.connect(self.run_doctor)
        file_menu.addAction(act_doctor)

        file_menu.addSeparator()

        act_exit = QAction("Thoát", self)
        act_exit.setShortcut("Ctrl+Q")
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        settings_menu = menubar.addMenu("&Cài Đặt")
        act_settings = QAction(icon("settings"), "Cấu hình AI & model…", self)
        act_settings.triggered.connect(self.open_settings)
        settings_menu.addAction(act_settings)

        view_menu = menubar.addMenu("&Hiển thị")
        for text, shortcut, callback in (
            ("Tìm tệp", "Ctrl+P", self.focus_file_search),
            ("Tập trung vào Agent", "Ctrl+L", self.focus_agent),
            ("Hiện / ẩn Agent", "Ctrl+Alt+A", self.toggle_agent),
            ("Hiện / ẩn Terminal", "Ctrl+J", self.toggle_terminal),
            ("Cuộc trò chuyện mới", "Ctrl+N", self.on_new_conversation_requested),
        ):
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(callback)
            view_menu.addAction(action)

        help_menu = menubar.addMenu("&Trợ Giúp")
        act_about = QAction("Giới Thiệu Graft Agent", self)
        act_about.triggered.connect(self.show_about)
        help_menu.addAction(act_about)

    def init_status_bar(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.setSizeGripEnabled(False)
        encoding = QLabel("UTF-8    ·    Graft")
        encoding.setObjectName("muted")
        self.status.addPermanentWidget(encoding)
        self.status.showMessage(f"Sẵn sàng | Codebase: {self.root_dir} | Model: {self.config.model}")

    def initial_setup(self):
        self.sidebar.reload_projects_list(self.root_dir)
        convs = self.session_mgr.get_conversations(self.current_project["id"])
        if convs:
            latest_id = convs[0]["id"]
            self.sidebar.reload_conversations(self.current_project["id"], select_conv_id=latest_id)
            self.on_conversation_selected(latest_id)
        else:
            self.on_new_conversation_requested()
        self.do_scan(welcome=False)

    def on_conversation_selected(self, conv_id: str):
        self.current_conv_id = conv_id
        conv = self.session_mgr.get_conversation(self.current_project["id"], conv_id)
        if conv:
            self.editor.chat_view.load_messages(conv.get("messages", []))
            self.status.showMessage(f"Hội thoại: {conv.get('title', '')} | Dự án: {self.current_project['name']}")

    def on_new_conversation_requested(self):
        conv = self.session_mgr.create_conversation(self.current_project["id"], title="Cuộc trò chuyện mới")
        self.current_conv_id = conv["id"]
        self.editor.chat_view.clear_chat()
        self.sidebar.reload_conversations(self.current_project["id"], select_conv_id=self.current_conv_id)
        self.focus_agent()
        self.status.showMessage("Đã tạo cuộc trò chuyện mới.")

    def on_rename_conversation_requested(self, conv_id: str, new_title: str):
        if self.session_mgr.rename_conversation(self.current_project["id"], conv_id, new_title):
            self.sidebar.reload_conversations(self.current_project["id"], select_conv_id=self.current_conv_id)
            self.status.showMessage(f"Đã đổi tên hội thoại thành: {new_title}")

    def on_delete_conversation_requested(self, conv_id: str):
        self.session_mgr.delete_conversation(self.current_project["id"], conv_id)
        convs = self.session_mgr.get_conversations(self.current_project["id"])
        if convs:
            next_id = convs[0]["id"]
            self.on_conversation_selected(next_id)
            self.sidebar.reload_conversations(self.current_project["id"], select_conv_id=next_id)
        else:
            self.on_new_conversation_requested()
        self.status.showMessage("Đã xóa cuộc trò chuyện.")

    def on_message_persisted(self, msg: dict):
        if not self.current_conv_id:
            conv = self.session_mgr.create_conversation(self.current_project["id"])
            self.current_conv_id = conv["id"]

        self.session_mgr.append_message(self.current_project["id"], self.current_conv_id, msg)
        self.sidebar.reload_conversations(self.current_project["id"], select_conv_id=self.current_conv_id)

    def switch_workspace(self, folder_path: str):
        folder_path = os.path.abspath(folder_path)
        if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            QMessageBox.warning(self, "Lỗi", f"Thư mục không tồn tại:\n{folder_path}")
            return

        self.root_dir = folder_path
        self.current_project = self.session_mgr.get_or_create_project(self.root_dir)
        self.agent = GraftAgent(self.config, self.root_dir)
        self.sidebar.agent = self.agent
        self.sidebar.tree.clear()
        self.sidebar.file_search.clear()
        self.sidebar.lbl_stats.setText("Đang quét dự án…")
        self.prompt.update_file_list([])
        self.prompt.btn_undo.setEnabled(False)
        self.update_workspace_header()
        self.editor.current_file = None
        self.editor.code_editor.clear()
        self.editor.set_diff("")
        self.editor.pages.setCurrentIndex(0)

        self.sidebar.reload_projects_list(self.root_dir)
        convs = self.session_mgr.get_conversations(self.current_project["id"])
        if convs:
            self.current_conv_id = convs[0]["id"]
            self.sidebar.reload_conversations(self.current_project["id"], select_conv_id=self.current_conv_id)
            self.on_conversation_selected(self.current_conv_id)
        else:
            self.on_new_conversation_requested()

        self.status.showMessage(f"Đã chuyển sang dự án: {self.root_dir}")
        self.do_scan(welcome=False)

    def update_codebase_views(self):
        """Cập nhật cây tệp và danh sách symbols trên giao diện tức thì mà không cần spawn luồng ngầm."""
        try:
            self.sidebar.update_tree()
            self.prompt.update_file_list(list(self.agent.graph.files.keys()))
            self.prompt.btn_undo.setEnabled(len(self.agent.history_backups) > 0)
            symbols_count = sum(len(f.symbols) for f in self.agent.graph.files.values())
            self.status.showMessage(
                f"Codebase: {self.root_dir} | {len(self.agent.graph.files)} tệp | {symbols_count} biểu tượng AST | Sẵn sàng"
            )
        except Exception:
            pass

    def do_scan(self, welcome: bool = False):
        if self.scan_worker is not None:
            if self.scan_worker.agent is not self.agent:
                self._pending_scan_welcome = welcome
                self.status.showMessage("Đang chờ lượt quét trước kết thúc để quét dự án mới…")
            return
        self.status.showMessage("Đang quét AST biểu tượng & đồ thị codebase...")
        self.scan_worker = ScanWorker(self.agent, welcome=welcome)
        self.scan_worker.finished.connect(self.on_scan_completed)
        self.scan_worker.start()

    @Slot()
    def on_scan_completed(self):
        worker = self.sender()
        if worker is not self.scan_worker:
            return
        self.scan_worker = None
        # The native QThread signal runs this slot on the UI thread after scanning stops.
        # A result from an earlier workspace must never update the current explorer.
        if worker.agent is self.agent:
            if worker.error_message is not None:
                self.on_scan_error(worker.error_message)
            else:
                self.on_scan_finished(worker.stats, welcome=worker.welcome)
        worker.deleteLater()
        if self._pending_scan_welcome is not None:
            welcome = self._pending_scan_welcome
            self._pending_scan_welcome = None
            self.do_scan(welcome=welcome)

    def on_scan_finished(self, stats: dict, welcome: bool = False):
        self.sidebar.update_tree()
        self.prompt.update_file_list(list(self.agent.graph.files.keys()))
        self.prompt.btn_undo.setEnabled(len(self.agent.history_backups) > 0)
        self.status.showMessage(
            f"Codebase: {self.root_dir} | {stats['files_count']} tệp | {stats['symbols_count']} biểu tượng AST | Sẵn sàng"
        )

        if welcome:
            folder_name = os.path.basename(self.root_dir)
            self.editor.chat_view.add_system_message(
                f"🚀 ĐÃ KÍCH HOẠT GRAFT CODE AGENT: {folder_name}",
                f"• <b>Đường dẫn:</b> <code>{self.root_dir}</code><br>"
                f"• <b>Đã lập chỉ mục AST:</b> <b>{stats['files_count']}</b> tệp | <b>{stats['symbols_count']}</b> hàm & lớp.<br>"
                f"• <b>Tư duy Kỹ sư Cao cấp:</b> Đã kích hoạt <code>SENIOR_ENGINEERING_RULES.md</code> (Andrej Karpathy & Addy Osmani Disciplines).<br>"
                f"• <b>Chẩn đoán tự động:</b> Nhấn nút <code>🩺 Doctor</code> hoặc phím <b>F6</b> để kiểm tra ngay môi trường máy tính và tình trạng thư viện dự án.<br>"
                f"• <b>Sẵn sàng phục vụ:</b> Bạn có thể hỏi đáp dự án, kiểm tra thiếu sót, cấy ghép mã nguồn hoặc khởi chạy tiến trình."
            )

    def on_scan_error(self, err: str):
        self.sidebar.lbl_stats.setText("Quét dự án thất bại")
        self.status.showMessage(f"Lỗi quét AST: {err}")
        QMessageBox.warning(self, "Lỗi quét Codebase", err)

    def on_file_selected(self, relative_path: str):
        full_path = self.agent.root_dir / relative_path
        if full_path.exists() and full_path.is_file():
            try:
                content = full_path.read_text(encoding="utf-8-sig", errors="replace")
                self.editor.set_file_content(relative_path, content)
                self.prompt.target_file_combo.setCurrentIndex(
                    self.prompt.target_file_combo.findData(relative_path)
                )
            except Exception as e:
                QMessageBox.warning(self, "Lỗi đọc file", str(e))

    def on_symbol_selected(self, relative_path: str, start_line: int, end_line: int):
        self.on_file_selected(relative_path)
        self.editor.set_file_content(relative_path, self.editor.code_editor.toPlainText(), line_number=start_line)

    def on_graft_requested(self, task: str, target_file: str, options: dict):
        images = options.get("images", [])
        self.config.thinking = options.get("thinking", True)
        self.config.dual_ai_mode = options.get("dual_ai", False)
        self.config.auto_apply = options.get("auto_apply", False)

        self.current_task = task
        self.loop_goal = task
        self.feedback_loop_count = 0
        self.feedback_loop_active = True
        self.editor.chat_view.add_user_message(task, images=images)
        self.editor.show_chat()

        self.prompt.btn_graft.setEnabled(False)
        self.prompt.btn_apply.setEnabled(False)
        status_msg = "AI Gateway đang phân tích văn bản & hình ảnh..." if images else "AI Gateway đang phân tích và xử lý..."
        self.status.showMessage(status_msg)

        if hasattr(self, "graft_worker") and self.graft_worker and self.graft_worker.isRunning():
            self.graft_worker.wait(1000)

        self.graft_worker = GraftWorker(self.agent, task, target_file, images=images)
        self.graft_worker.finished.connect(self.on_graft_finished)
        self.graft_worker.error.connect(self.on_graft_error)
        self.graft_worker.start()

    def on_graft_finished(self, res: dict):
        self.prompt.btn_graft.setEnabled(True)
        tokens = res.get("tokens", {})
        self.prompt.set_tokens(tokens)

        if not res.get("success"):
            err_msg = res.get("error", "Lỗi không xác định từ AI Gateway")
            self.status.showMessage(f"Thất bại: {err_msg}")
            self.editor.chat_view.add_system_message("❌ LỖI TỪ AI GATEWAY", err_msg)
            return

        actions = res.get("actions", [])
        create_files = res.get("create_files", [])
        delete_files = res.get("delete_files", [])
        commands = res.get("commands", [])
        ai_response = res.get("response", "")

        self.last_actions = actions
        self.pending_creates = create_files

        is_auto = self.config.auto_apply or self.prompt.chk_auto.isChecked()

        # TỰ ĐỘNG THỰC HIỆN NGAY LẬP TỨC (nếu bật Tự động áp dụng)
        if is_auto:
            has_changes = False
            if create_files:
                for cf in create_files:
                    succ, msg = self.agent.create_new_file(cf["file"], cf["code"])
                    if succ:
                        self.editor.chat_view.add_system_message("📝 TỰ ĐỘNG TẠO FILE", f"Đã tạo file mới: <code>{cf['file']}</code><br><a href='open_file:{cf['file']}'>Mở xem file</a>")
                        self.prompt.btn_undo.setEnabled(True)
                        has_changes = True

            if actions:
                for act in actions:
                    if act.get("success"):
                        self.agent.apply_action(act)
                        self.editor.chat_view.add_system_message("💾 TỰ ĐỘNG CẤY GHÉP", f"Đã cập nhật sửa file: <code>{act['file']}</code>")
                        self.prompt.btn_undo.setEnabled(True)
                        has_changes = True

            if has_changes:
                self.update_codebase_views()

        self.editor.chat_view.add_ai_message(
            ai_response,
            graft_actions=actions,
            create_files=create_files,
            delete_files=delete_files,
            commands=commands,
            tokens=tokens,
            auto_applied=is_auto
        )

        if actions and not is_auto:
            first_act = actions[0]
            if first_act.get("success"):
                self.editor.set_diff(first_act.get("diff", ""))
                self.status.showMessage(f"Cấy ghép thành công: {first_act.get('msg')} | Nhấn [Áp Dụng] để lưu.")
                self.prompt.btn_apply.setEnabled(True)

        task_lower = getattr(self, "current_task", "").lower()
        should_autorun = is_auto or any(kw in task_lower for kw in ["chạy", "run", "khởi động", "start", "cài", "install", "fix", "sửa"])

        if commands and should_autorun:
            first_cmd = commands[0]["command"]
            self.editor.chat_view.add_system_message(
                "🚀 ĐANG TỰ ĐỘNG THỰC THI TIẾN TRÌNH",
                f"• Đang thực thi lệnh: <code>{first_cmd}</code><br>"
                f"• <i>Hệ thống đang xử lý ngầm (đang tải/cài đặt). Khi lệnh kết thúc, AI sẽ <b>tự động phân tích log và chạy tiếp bước sau</b> mà bạn không cần phải gõ lệnh tiếp tục!</i>"
            )
            QTimer.singleShot(600, lambda: self.run_terminal_command(first_cmd))
        elif (actions or create_files) and is_auto and any(kw in task_lower for kw in ["chạy", "run", "khởi động", "start"]):
            try:
                insp = self.agent.doctor()
                plan = insp.get("action_plan", [])
                srv_cmds = [p for p in plan if p.get("type") == "START_SERVER" and p.get("cmd")]
                if srv_cmds:
                    run_cmd = srv_cmds[0]["cmd"]
                    self.editor.chat_view.add_system_message(
                        "🚀 TỰ ĐỘNG KHỞI CHẠY MÁY CHỦ SAU KHI SỬA FILE",
                        f"Đã cập nhật mã nguồn thành công. Đang tự động khởi chạy máy chủ: <code>{run_cmd}</code>..."
                    )
                    QTimer.singleShot(600, lambda: self.run_terminal_command(run_cmd))
            except Exception:
                pass
        elif commands:
            self.status.showMessage(f"AI đề xuất {len(commands)} lệnh Terminal. Nhấn vào thẻ lệnh trong Chat để chạy.")
        elif not actions and not create_files:
            self.status.showMessage("AI đã phản hồi xong.")

    def on_graft_error(self, err: str):
        self.prompt.btn_graft.setEnabled(True)
        self.status.showMessage(f"Lỗi kết nối AI: {err}")
        self.editor.chat_view.add_system_message("❌ LỖI KẾT NỐI", str(err))

    def on_chat_apply_clicked(self, data: dict):
        target_f = data.get("file")
        for act in self.last_actions:
            if act.get("file") == target_f and act.get("success"):
                self.apply_action(act)
                return

    def on_chat_view_diff_clicked(self, data: dict):
        target_f = data.get("file")
        for act in self.last_actions:
            if act.get("file") == target_f and act.get("success"):
                self.editor.set_diff(act.get("diff", ""))
                return

    def on_apply_requested(self):
        if not self.last_actions:
            return
        for act in self.last_actions:
            if act.get("success"):
                self.apply_action(act)

    def apply_action(self, action: dict):
        self.status.showMessage(f"Đang ghi thay đổi cấy ghép vào {action['file']}...")
        self.apply_worker = ApplyWorker(self.agent, action)
        self.apply_worker.finished.connect(self.on_apply_finished)
        self.apply_worker.start()

    def on_apply_finished(self, success: bool, msg: str):
        if success:
            self.status.showMessage(f"Thành công: {msg}")
            self.editor.chat_view.add_system_message("💾 ĐÃ ÁP DỤNG CẤY GHÉP", msg)
            self.prompt.btn_undo.setEnabled(True)
            self.prompt.btn_apply.setEnabled(False)
            self.update_codebase_views()
            if self.editor.current_file:
                self.on_file_selected(self.editor.current_file)
        else:
            self.status.showMessage(f"Lỗi áp dụng: {msg}")
            QMessageBox.critical(self, "Lỗi Áp Dụng", msg)

    def create_file_requested(self, file_path: str):
        for cf in self.pending_creates:
            if cf["file"] == file_path:
                succ, msg = self.agent.create_new_file(file_path, cf["code"])
                if succ:
                    self.editor.chat_view.add_system_message("📝 ĐÃ TẠO FILE THÀNH CÔNG", f"{msg}<br><a href='open_file:{file_path}'>Mở xem file</a>")
                    self.prompt.btn_undo.setEnabled(True)
                    self.update_codebase_views()
                    self.on_file_selected(file_path)
                else:
                    QMessageBox.warning(self, "Lỗi Tạo File", msg)
                return

    def delete_file_requested(self, file_path: str):
        reply = QMessageBox.question(
            self,
            "Xác Nhận Xóa File",
            f"Bạn có chắc muốn xóa file sau khỏi dự án?\n{file_path}\n(Hệ thống sẽ lưu bản backup để có thể Undo).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            succ, msg = self.agent.delete_project_file(file_path)
            if succ:
                self.editor.chat_view.add_system_message("🗑️ ĐÃ XÓA FILE", msg)
                self.prompt.btn_undo.setEnabled(True)
                self.update_codebase_views()
            else:
                QMessageBox.warning(self, "Lỗi Xóa File", msg)

    def run_terminal_command(self, cmd: str):
        self.editor.show_terminal()
        if self.process_runner.is_running():
            old_cmd = self.process_runner.current_cmd
            self.editor.chat_view.add_system_message(
                "🔄 TỰ ĐỘNG GIẢI PHÓNG TERMINAL",
                f"Đang dừng tiến trình cũ: <code>{old_cmd}</code> để thực thi lệnh mới: <code>{cmd}</code>..."
            )
        self.process_runner.run_command(cmd, str(self.root_dir))

    def on_process_started(self, cmd: str):
        self.editor.terminal_view.set_running(True)
        self.status.showMessage(f"Đang chạy tiến trình: {cmd}")

    def on_process_output(self, text: str, is_error: bool):
        self.editor.terminal_view.append_output(text, is_error)

    def on_process_finished(self, exit_code: int):
        self.editor.terminal_view.set_running(False)
        status_text = "Thành công" if exit_code == 0 else f"Lỗi (Exit: {exit_code})"
        self.status.showMessage(f"Tiến trình kết thúc: {status_text}")

    def on_stop_process_requested(self):
        self.feedback_loop_active = False
        self.process_runner.kill_process()
        self.editor.chat_view.add_system_message(
            "⏹ ĐÃ DỪNG TIẾN TRÌNH",
            "Bạn đã chủ động dừng tiến trình. Vòng lặp tự động đã được kết thúc."
        )

    def on_command_completed(self, cmd: str, exit_code: int, full_log: str):
        if not self.feedback_loop_active or not self.prompt.chk_feedback.isChecked():
            return

        # Kiểm tra nếu lệnh vừa kết thúc là lệnh chạy ứng dụng (GUI hoặc Script chính)
        # và đã kết thúc thành công (Exit Code: 0).
        # Khi người dùng đóng ứng dụng GUI, app.exec() trả về 0 -> tiến trình kết thúc sạch.
        # Ta cần dừng ngay vòng lặp để tránh việc AI tự động mở lại ứng dụng gây phiền toái.
        cmd_clean = cmd.strip()
        cmd_lower = cmd_clean.lower()

        is_script_run = bool(re.search(r'(?:python(?:\.exe)?|node(?:\.exe)?)\s+([^\s;&|]+\.(?:py|js))', cmd_clean, re.IGNORECASE))
        is_app_keyword = any(kw in cmd_lower for kw in ["main.py", "app.py", "run.py", "gui.py", "start.py", "index.js", "npm start", "run.bat"])
        is_helper_cmd = any(h in cmd_lower for h in [
            "pip ", "pip.exe", "install", "pytest", "unittest",
            "dir", "cat ", "type ", "echo ", "get-content", "findstr", "grep",
            "git ", "curl", "wget", "composer ", "node_modules", "npm install"
        ])

        has_critical_error = bool(re.search(r'Traceback \(most recent call last\):|ModuleNotFoundError:|ImportError:|SyntaxError:', full_log))

        if (is_script_run or is_app_keyword) and not is_helper_cmd and exit_code == 0 and not has_critical_error:
            self.feedback_loop_active = False
            self.editor.chat_view.add_system_message(
                "🎉 ỨNG DỤNG ĐÃ HOÀN TẤT PHIÊN LÀM VIỆC",
                f"Tiến trình <code>{cmd}</code> đã kết thúc thành công (Mã thoát: 0).<br>"
                "Người dùng đã đóng ứng dụng hoặc tiến trình hoàn tất bình thường.<br>"
                "Hệ thống đã tự động dừng vòng lặp để không tự động mở lại ứng dụng."
            )
            return

        self.start_agent_feedback_step(cmd, exit_code, full_log)

    def start_agent_feedback_step(self, cmd: str, exit_code: int, full_log: str):
        if self.feedback_loop_count >= self.max_feedback_loops:
            self.feedback_loop_active = False
            self.editor.chat_view.add_system_message(
                "⚠️ ĐÃ ĐẠT GIỚI HẠN BƯỚC TỰ ĐỘNG",
                f"Đã thực hiện xong {self.max_feedback_loops} bước lặp tự động. Bạn có thể kiểm tra Terminal hoặc yêu cầu tiếp."
            )
            return

        self.feedback_loop_count += 1
        step_num = self.feedback_loop_count
        self.status.showMessage(f"🤖 AI đang đọc log Terminal của lệnh `{cmd}` (Bước {step_num}/{self.max_feedback_loops})...")

        self.editor.chat_view.add_system_message(
            f"🤖 AI ĐANG PHÂN TÍCH LOG TERMINAL (Bước {step_num}/{self.max_feedback_loops})",
            f"• Lệnh vừa kết thúc: <code>{cmd}</code> (Mã thoát: {exit_code})<br>"
            f"• AI đang phân tích log thời gian thực để gửi lệnh tiếp theo..."
        )

        if hasattr(self, "feedback_worker") and self.feedback_worker and self.feedback_worker.isRunning():
            self.feedback_worker.wait(1000)

        self.feedback_worker = AgentFeedbackWorker(
            self.agent, self.loop_goal, cmd, exit_code, full_log
        )
        self.feedback_worker.finished.connect(self.on_feedback_finished)
        self.feedback_worker.error.connect(self.on_feedback_error)
        self.feedback_worker.start()

    def on_feedback_finished(self, res: dict):
        if not res.get("success"):
            self.feedback_loop_active = False
            self.editor.chat_view.add_system_message("❌ LỖI PHÂN TÍCH LOG", res.get("error", ""))
            return

        ai_response = res.get("response", "")
        commands = res.get("commands", [])
        actions = res.get("actions", [])
        create_files = res.get("create_files", [])
        delete_files = res.get("delete_files", [])
        tokens = res.get("tokens", {})

        self.editor.chat_view.add_ai_message(
            ai_response,
            graft_actions=actions,
            create_files=create_files,
            delete_files=delete_files,
            commands=commands,
            tokens=tokens,
            auto_applied=True
        )

        has_changes = False
        if actions:
            for act in actions:
                if act.get("success"):
                    self.agent.apply_action(act)
                    self.editor.chat_view.add_system_message("🛠️ TỰ ĐỘNG SỬA CODE", f"Đã cấy ghép sửa lỗi vào <code>{act['file']}</code>")
                    self.prompt.btn_undo.setEnabled(True)
                    has_changes = True

        if create_files:
            for cf in create_files:
                succ, msg = self.agent.create_new_file(cf["file"], cf["code"])
                if succ:
                    self.editor.chat_view.add_system_message("📝 TỰ ĐỘNG TẠO FILE", f"Đã tạo file mới: <code>{cf['file']}</code>")
                    self.prompt.btn_undo.setEnabled(True)
                    has_changes = True

        if has_changes:
            self.update_codebase_views()

        if commands:
            next_cmd = commands[0]["command"]
            self.editor.chat_view.add_system_message(
                "🚀 TIẾP TỤC CHẠY BƯỚC TIẾP THEO",
                f"Lệnh: <code>{next_cmd}</code>"
            )
            QTimer.singleShot(800, lambda: self.run_terminal_command(next_cmd))
        elif (actions or create_files) and self.process_runner.current_cmd:
            retry_cmd = self.process_runner.current_cmd
            self.editor.chat_view.add_system_message(
                "🔄 TỰ ĐỘNG KHỞI CHẠY LẠI MÁY CHỦ ĐỂ KIỂM TRA MÃ NGUỒN VỪA SỬA",
                f"Đã cập nhật mã nguồn thành công. Đang tự động chạy lại lệnh: <code>{retry_cmd}</code> để kiểm tra phản hồi ứng dụng..."
            )
            QTimer.singleShot(800, lambda: self.run_terminal_command(retry_cmd))
        else:
            self.feedback_loop_active = False
            self.editor.chat_view.add_system_message(
                "🎉 HOÀN TẤT TIẾN TRÌNH",
                "AI đã điều phối xong tất cả các bước theo yêu cầu của bạn!"
            )

    def on_feedback_error(self, err: str):
        self.feedback_loop_active = False
        self.editor.chat_view.add_system_message("❌ LỖI VÒNG LẶP AGENT", str(err))

    def on_server_detected(self, cmd: str, server_url: str):
        self.status.showMessage(f"Đang kiểm tra kết nối máy chủ: {server_url}...")
        self.editor.chat_view.add_system_message(
            "🌐 ĐANG KIỂM TRA PHẢN HỒI MÁY CHỦ (HEALTH CHECK)",
            f"• Máy chủ phát hiện tại: <code>{server_url}</code><br>"
            f"• Lệnh chạy: <code>{cmd}</code><br>"
            f"• AI đang gửi yêu cầu kiểm tra xem trang chủ có tải thành công (HTTP 200) hay không..."
        )

        if hasattr(self, "probe_worker") and self.probe_worker and self.probe_worker.isRunning():
            self.probe_worker.wait(1000)

        self.probe_worker = ServerHealthProbeWorker(server_url, delay_ms=1000)
        self.probe_worker.finished.connect(lambda res: self.on_probe_finished(cmd, server_url, res))
        self.probe_worker.start()

    def on_probe_finished(self, cmd: str, server_url: str, res: dict):
        is_healthy = res.get("is_healthy", False)
        status_code = res.get("status_code")
        error_msg = res.get("error", "")

        if is_healthy:
            self.feedback_loop_active = False
            self.status.showMessage(f"Máy chủ đã sẵn sàng: {server_url} (HTTP {status_code} OK)")
            self.editor.chat_view.add_system_message(
                "🌟 MÁY CHỦ ĐÃ KHỞI ĐỘNG & HOẠT ĐỘNG HOÀN HẢO!",
                f"• Lệnh chạy: <code>{cmd}</code><br>"
                f"• Phản hồi: <b>HTTP {status_code} OK</b><br>"
                f"• Địa chỉ truy cập: <b><a href='{server_url}'>{server_url}</a></b><br>"
                f"• Tiến trình máy chủ đang duy trì ổn định trong Tab Terminal."
            )
        else:
            if not self.feedback_loop_active:
                self.feedback_loop_active = True
                self.feedback_loop_count = 0
                self.loop_goal = f"Khắc phục lỗi máy chủ {cmd} không phản hồi đúng (HTTP {status_code})"

            self.editor.chat_view.add_system_message(
                f"⚠️ PHÁT HIỆN MÁY CHỦ BÁO LỖI (HTTP {status_code or 'Không kết nối'})",
                f"• Truy cập thử <code>{server_url}</code> thất bại: <i>{error_msg}</i><br>"
                f"• AI đang dừng máy chủ cũ để tự động phân tích log và sửa cấu hình/code..."
            )
            self.process_runner.kill_process(silent_for_restart=True)
            full_log = self.process_runner.full_log + f"\n[HEALTH_PROBE_ERROR]: HTTP {status_code} - {error_msg}\n{res.get('snippet', '')}\n"
            self.start_agent_feedback_step(cmd, 1, full_log)

    def on_undo_requested(self):
        reply = QMessageBox.question(
            self,
            "Xác Nhận Hoàn Tác",
            "Bạn có chắc muốn hoàn tác thay đổi cấy ghép hoặc thao tác file gần nhất?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.undo_worker = UndoWorker(self.agent)
            self.undo_worker.finished.connect(self.on_undo_finished)
            self.undo_worker.start()

    def on_undo_finished(self, success: bool, msg: str):
        if success:
            self.editor.chat_view.add_system_message("↩️ HOÀN TÁC THÀNH CÔNG", msg)
            self.prompt.btn_undo.setEnabled(len(self.agent.history_backups) > 0)
            self.update_codebase_views()
            if self.editor.current_file:
                self.on_file_selected(self.editor.current_file)
        else:
            QMessageBox.warning(self, "Lỗi Hoàn Tác", msg)

    def run_doctor(self):
        if hasattr(self, "doctor_worker") and self.doctor_worker and self.doctor_worker.isRunning():
            return
        self.status.showMessage("Đang kiểm tra môi trường máy tính & tình trạng dự án...")
        self.editor.chat_view.add_system_message(
            "🩺 ĐANG CHẨN ĐOÁN DỰ ÁN & MÔI TRƯỜNG MÁY TÍNH",
            f"Đang kiểm tra các runtime trên máy (PHP, Node, Python, Composer...) và quét thư viện tệp cấu hình của: <code>{self.root_dir}</code>..."
        )
        self.doctor_worker = DoctorWorker(self.agent)
        self.doctor_worker.finished.connect(self.on_doctor_finished)
        self.doctor_worker.error.connect(self.on_doctor_error)
        self.doctor_worker.start()

    def on_doctor_finished(self, rep: dict):
        self.status.showMessage("Đã hoàn tất kiểm tra chẩn đoán.")
        markdown_text = rep.get("markdown_report", "")

        action_plan = rep.get("action_plan", [])
        commands = []
        for act in action_plan:
            cmd = act.get("cmd")
            if cmd:
                commands.append({
                    "command": cmd,
                    "description": f"{act.get('name')}: {act.get('desc')}"
                })

        self.editor.chat_view.add_ai_message(
            markdown_text,
            commands=commands
        )

        missing_r = rep.get("missing_runtimes", [])
        if missing_r:
            r_names = ", ".join(m["name"] for m in missing_r)
            QMessageBox.warning(
                self,
                "Thiếu Công Cụ / Ngôn Ngữ Trên Máy",
                f"Máy tính của bạn đang thiếu các công cụ cần thiết cho dự án:\n- {r_names}\n\nVui lòng xem hướng dẫn cài đặt trong cửa sổ Chat."
            )

    def on_doctor_error(self, err: str):
        self.status.showMessage(f"Lỗi chẩn đoán: {err}")
        self.editor.chat_view.add_system_message("❌ LỖI CHẨN ĐOÁN DỰ ÁN", str(err))

    def open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            self.agent.config = self.config
            self.prompt.set_model(self.config.model)
            self.prompt.chk_thinking.setChecked(self.config.thinking)
            self.prompt.chk_dual.setChecked(self.config.dual_ai_mode)
            self.prompt.chk_auto.setChecked(self.config.auto_apply)
            self.status.showMessage(f"Đã cập nhật cấu hình | Model: {self.config.model}")

    def show_about(self):
        QMessageBox.about(
            self,
            "Về Graft Code Agent",
            "<h3>🚀 Graft Code Agent (Autonomous Studio)</h3>"
            "<p>Trợ lý lập trình AI phẫu thuật cấy ghép mã nguồn kết hợp đồ thị AST Codebase.</p>"
            "<p><b>Tính năng chính:</b></p>"
            "<ul>"
            "<li>Import mọi folder dự án từ máy tính & tự kích hoạt Graft</li>"
            "<li>Hỏi đáp kiến trúc, tìm thông tin dự án qua Chat</li>"
            "<li>Surgical AST Grafting (không làm hỏng code cũ)</li>"
            "<li>Tạo file mới, xóa file an toàn với sao lưu Undo</li>"
            "<li>Terminal thực thi tiến trình hệ thống trực tiếp</li>"
            "</ul>"
        )
