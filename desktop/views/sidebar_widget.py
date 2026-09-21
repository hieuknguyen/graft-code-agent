import os
from datetime import datetime
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QFileDialog,
    QStackedWidget, QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
    QMenu, QHeaderView
)
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QColor

from desktop.icons import icon

from core.agent import GraftAgent
from core.session_manager import SessionManager

class SidebarWidget(QWidget):
    project_switched = Signal(str) # folder_path
    project_conversation_selected = Signal(str, str)
    settings_requested = Signal()
    sidebar_toggle_requested = Signal()
    conversation_selected = Signal(str) # conv_id
    new_conversation_requested = Signal()
    rename_conversation_requested = Signal(str, str) # conv_id, new_title
    delete_conversation_requested = Signal(str) # conv_id
    delete_project_requested = Signal(str) # project_id

    file_selected = Signal(str)
    symbol_selected = Signal(str, int, int) # file, start_line, end_line
    doctor_requested = Signal()
    rescan_requested = Signal()

    def __init__(self, agent: GraftAgent, session_mgr: SessionManager, parent=None):
        super().__init__(parent)
        self.agent = agent
        self.session_mgr = session_mgr
        self.current_conv_id: Optional[str] = None
        self.init_ui()

    def init_ui(self):
        self.setObjectName("sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(245)
        self.setMaximumWidth(405)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 12)
        main_layout.setSpacing(6)
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(8, 0, 4, 10)
        mark = QLabel()
        mark.setPixmap(icon("spark", "#d1d1d1", 25).pixmap(25, 25))
        brand_row.addWidget(mark)
        brand = QLabel("Graft")
        brand.setObjectName("brand")
        brand_row.addWidget(brand)
        brand_row.addStretch()
        collapse = QPushButton(icon("panel"), "")
        collapse.setObjectName("iconButton")
        collapse.setFixedSize(30, 30)
        collapse.setToolTip("Thu gọn thanh bên")
        collapse.clicked.connect(self.sidebar_toggle_requested.emit)
        brand_row.addWidget(collapse)
        main_layout.addLayout(brand_row)

        self.btn_new_chat = QPushButton(icon("plus"), "Cuộc trò chuyện mới")
        self.btn_new_chat.setObjectName("newConversation")
        self.btn_new_chat.setMinimumHeight(40)
        self.btn_new_chat.clicked.connect(self.new_conversation_requested.emit)
        main_layout.addWidget(self.btn_new_chat)
        self.btn_history = QPushButton(icon("history"), "Lịch sử hội thoại")
        self.btn_history.setObjectName("navButton")
        self.btn_history.clicked.connect(self.show_history)
        main_layout.addWidget(self.btn_history)
        self.btn_explorer = QPushButton(icon("folder"), "Tệp trong dự án")
        self.btn_explorer.setObjectName("navButton")
        self.btn_explorer.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        main_layout.addWidget(self.btn_explorer)
        main_layout.addSpacing(18)

        self.tabs = QStackedWidget()
        home = QWidget()
        home.setObjectName("sidebarPage")
        home_layout = QVBoxLayout(home)
        home_layout.setContentsMargins(0, 0, 0, 0)
        home_layout.setSpacing(8)
        self.conv_search = QLineEdit()
        self.conv_search.setObjectName("sidebarSearch")
        self.conv_search.setPlaceholderText("Tìm hội thoại hoặc dự án…")
        self.conv_search.textChanged.connect(self.filter_conversations)
        self.conv_search.hide()
        home_layout.addWidget(self.conv_search)
        recent_label = QLabel("Hội thoại gần đây")
        recent_label.setObjectName("sectionLabel")
        home_layout.addWidget(recent_label)
        self.conv_list = QListWidget()
        self.conv_list.setObjectName("recentConversations")
        self.conv_list.setFixedHeight(88)
        self.conv_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.conv_list.itemClicked.connect(self.on_conv_item_clicked)
        self.conv_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.conv_list.customContextMenuRequested.connect(self.show_conv_context_menu)
        home_layout.addWidget(self.conv_list)
        home_layout.addSpacing(12)
        projects_header = QHBoxLayout()
        projects_label = QLabel("Dự án")
        projects_label.setObjectName("sectionLabel")
        projects_header.addWidget(projects_label)
        projects_header.addStretch()
        self.btn_import = QPushButton(icon("folder_plus"), "")
        self.btn_import.setObjectName("iconButton")
        self.btn_import.setFixedSize(28, 28)
        self.btn_import.setToolTip("Mở thư mục dự án (Ctrl+O)")
        self.btn_import.setAccessibleName("Mở thư mục dự án")
        self.btn_import.clicked.connect(self.browse_folder)
        projects_header.addWidget(self.btn_import)
        home_layout.addLayout(projects_header)
        self.projects_tree = QTreeWidget()
        self.projects_tree.setObjectName("projectTree")
        self.projects_tree.setHeaderHidden(True)
        self.projects_tree.setColumnCount(2)
        self.projects_tree.setRootIsDecorated(False)
        self.projects_tree.setIndentation(20)
        self.projects_tree.setUniformRowHeights(True)
        self.projects_tree.header().setStretchLastSection(False)
        self.projects_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.projects_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.projects_tree.setColumnWidth(1, 52)
        self.projects_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.projects_tree.itemClicked.connect(self.on_project_item_clicked)
        self.projects_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.projects_tree.customContextMenuRequested.connect(self.show_project_context_menu)
        home_layout.addWidget(self.projects_tree, 1)
        self.tabs.addWidget(home)

        tab_files = QWidget()
        tab_files.setObjectName("sidebarPage")
        files_layout = QVBoxLayout(tab_files)
        files_layout.setContentsMargins(0, 0, 0, 0)
        files_layout.setSpacing(8)
        explorer_header = QHBoxLayout()
        back = QPushButton(icon("back"), "Dự án")
        back.setObjectName("iconButton")
        back.clicked.connect(lambda: self.tabs.setCurrentIndex(0))
        explorer_header.addWidget(back)
        explorer_header.addStretch()
        for attr, name, tooltip, signal in (
            ("btn_rescan", "refresh", "Quét lại codebase (F5)", self.rescan_requested),
            ("btn_doctor", "activity", "Kiểm tra môi trường (F6)", self.doctor_requested),
        ):
            button = QPushButton(icon(name), "")
            button.setObjectName("iconButton")
            button.setFixedSize(28, 28)
            button.setToolTip(tooltip)
            button.clicked.connect(signal.emit)
            setattr(self, attr, button)
            explorer_header.addWidget(button)
        files_layout.addLayout(explorer_header)
        self.file_search = QLineEdit()
        self.file_search.setObjectName("sidebarSearch")
        self.file_search.setPlaceholderText("Tìm tệp, hàm, class…")
        self.file_search.textChanged.connect(self.filter_tree)
        files_layout.addWidget(self.file_search)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(2)
        self.tree.setColumnHidden(1, True)
        self.tree.setIndentation(14)
        self.tree.setUniformRowHeights(True)
        self.tree.itemClicked.connect(self.on_tree_item_clicked)
        self.tree.itemDoubleClicked.connect(self.on_tree_item_double_clicked)
        files_layout.addWidget(self.tree)
        self.lbl_stats = QLabel("Chưa lập chỉ mục")
        self.lbl_stats.setObjectName("muted")
        files_layout.addWidget(self.lbl_stats)
        self.tabs.addWidget(tab_files)
        main_layout.addWidget(self.tabs, 1)
        settings = QPushButton(icon("settings"), "Cài đặt")
        settings.setObjectName("navButton")
        settings.clicked.connect(self.settings_requested.emit)
        main_layout.addWidget(settings)
        self.reload_projects_list(str(self.agent.root_dir))

    def show_history(self):
        self.tabs.setCurrentIndex(0)
        self.conv_search.show()
        self.conv_search.setFocus()

    def reload_projects_list(self, active_path: str):
        self.active_path = os.path.abspath(active_path)
        self.reload_project_tree()

    @staticmethod
    def relative_time(value):
        try:
            seconds = max(0, int((datetime.now() - datetime.strptime(value, "%Y-%m-%d %H:%M:%S")).total_seconds()))
        except (ValueError, TypeError):
            return ""
        if seconds < 60:
            return "0p"
        if seconds < 3600:
            return f"{seconds // 60}p"
        if seconds < 86400:
            return f"{seconds // 3600}g"
        return f"{seconds // 86400}n"

    def reload_project_tree(self):
        self.projects_tree.clear()
        for project in self.session_mgr.get_projects():
            folder = QTreeWidgetItem(self.projects_tree, [project["name"], ""])
            folder.setIcon(0, icon("folder", "#777777"))
            folder.setToolTip(0, project["path"])
            folder.setData(0, Qt.ItemDataRole.UserRole, {"type": "project", "path": project["path"]})
            active = os.path.abspath(project["path"]) == self.active_path
            folder.setForeground(0, QColor("#bfbfbf" if active else "#858585"))
            folder.setExpanded(True)
            for conv in self.session_mgr.get_conversations(project["id"]):
                if conv["message_count"] == 0 and conv["title"] == "Cuộc trò chuyện mới":
                    continue
                item = QTreeWidgetItem(folder, [conv["title"], self.relative_time(conv["updated_at"])])
                item.setToolTip(0, conv["title"])
                item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item.setForeground(1, QColor("#737373"))
                item.setData(0, Qt.ItemDataRole.UserRole, {
                    "type": "conversation", "path": project["path"], "id": conv["id"], "title": conv["title"]
                })
                if active and conv["id"] == self.current_conv_id:
                    self.projects_tree.setCurrentItem(item)

    def on_project_item_clicked(self, item, column):
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if data.get("type") == "conversation":
            self.project_conversation_selected.emit(data["path"], data["id"])
        elif data.get("type") == "project" and os.path.abspath(data["path"]) != self.active_path:
            self.project_switched.emit(data["path"])

    def show_project_context_menu(self, pos):
        item = self.projects_tree.itemAt(pos)
        data = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if data and data.get("type") == "conversation":
            # Switching first keeps rename/delete routed to the conversation's project.
            self.project_conversation_selected.emit(data["path"], data["id"])
            self.conversation_menu(data, self.projects_tree.mapToGlobal(pos))
        elif data and data.get("type") == "project":
            p_path = data.get("path")
            proj = next((p for p in self.session_mgr.get_projects() if os.path.abspath(p["path"]) == os.path.abspath(p_path)), None)
            if proj:
                menu = QMenu(self)
                act_switch = menu.addAction(icon("folder"), "Mở Dự Án Này")
                act_delete = menu.addAction(icon("trash"), "🗑️ Xóa Dự Án Khỏi Danh Sách")
                action = menu.exec(self.projects_tree.mapToGlobal(pos))
                if action == act_switch:
                    self.project_switched.emit(proj["path"])
                elif action == act_delete:
                    reply = QMessageBox.question(
                        self,
                        "Xác Nhận Xóa Dự Án Khỏi Danh Sách",
                        f"Bạn có chắc muốn xóa dự án '{proj['name']}' khỏi danh sách quản lý?\n(Thư mục thực tế trên ổ đĩa sẽ không bị ảnh hưởng).",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        self.delete_project_requested.emit(proj["id"])

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Chọn thư mục dự án cần cấy ghép code",
            str(self.agent.root_dir)
        )
        if folder:
            self.project_switched.emit(os.path.abspath(folder))

    # ==================== CONVERSATION ACTIONS ====================

    def reload_conversations(self, project_id: str, select_conv_id: Optional[str] = None):
        """Nạp danh sách cuộc trò chuyện cho project_id."""
        self.conv_list.clear()
        convs = self.session_mgr.get_conversations(project_id)

        selected_item = None
        for c in convs:
            if c["message_count"] == 0 and c["title"] == "Cuộc trò chuyện mới":
                continue
            c_id = c["id"]
            title = c.get("title", "Cuộc trò chuyện mới")
            item = QListWidgetItem(self.conv_list)
            item.setText(title)
            item.setToolTip(title)
            item.setData(Qt.ItemDataRole.UserRole, c)

            if select_conv_id and c_id == select_conv_id:
                selected_item = item
            elif selected_item is None and select_conv_id is None:
                selected_item = item

        if selected_item:
            self.conv_list.setCurrentItem(selected_item)
            c_data = selected_item.data(Qt.ItemDataRole.UserRole)
            self.current_conv_id = c_data["id"]
        else:
            self.current_conv_id = select_conv_id
        self.reload_project_tree()
        self.filter_conversations(self.conv_search.text())

    def on_conv_item_clicked(self, item: QListWidgetItem):
        c_data = item.data(Qt.ItemDataRole.UserRole)
        if c_data:
            c_id = c_data["id"]
            self.current_conv_id = c_id
            self.conversation_selected.emit(c_id)
            self.reload_project_tree()

    def filter_conversations(self, query: str):
        q = query.strip().lower()
        for i in range(self.conv_list.count()):
            item = self.conv_list.item(i)
            c_data = item.data(Qt.ItemDataRole.UserRole)
            title = c_data.get("title", "").lower() if c_data else ""
            item.setHidden(bool(q and q not in title))
        for i in range(self.projects_tree.topLevelItemCount()):
            project = self.projects_tree.topLevelItem(i)
            project_matches = not q or q in project.text(0).lower()
            visible = project_matches
            for j in range(project.childCount()):
                conversation = project.child(j)
                matches = project_matches or q in conversation.text(0).lower()
                conversation.setHidden(not matches)
                visible = visible or matches
            project.setHidden(not visible)

    def show_conv_context_menu(self, pos: QPoint):
        item = self.conv_list.itemAt(pos)
        if not item:
            return

        c_data = item.data(Qt.ItemDataRole.UserRole)
        self.conversation_menu(c_data, self.conv_list.mapToGlobal(pos))

    def conversation_menu(self, c_data, global_pos):
        c_id = c_data["id"]
        c_title = c_data.get("title", "Cuộc trò chuyện")

        menu = QMenu(self)
        act_rename = menu.addAction("✏️ Đổi Tên Hội Thoại")
        act_delete = menu.addAction("🗑️ Xóa Hội Thoại Này")

        action = menu.exec(global_pos)
        if action == act_rename:
            new_title, ok = QInputDialog.getText(
                self, "Đổi Tên Cuộc Trò Chuyện", "Nhập tiêu đề mới:", text=c_title
            )
            if ok and new_title.strip():
                self.rename_conversation_requested.emit(c_id, new_title.strip())

        elif action == act_delete:
            reply = QMessageBox.question(
                self,
                "Xác Nhận Xóa Hội Thoại",
                f"Bạn có chắc muốn xóa cuộc trò chuyện sau khỏi máy tính?\n\n\"{c_title}\"\n\n(Hành động này sẽ xóa file lưu trữ cục bộ).",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.delete_conversation_requested.emit(c_id)

    # ==================== FILE & AST ACTIONS ====================

    def update_tree(self):
        self.tree.clear()
        files = self.agent.graph.files
        total_symbols = 0
        folders = {}
        file_icon, folder_icon = icon("code"), icon("folder")
        for fpath, fast in sorted(files.items()):
            parts = fpath.replace("\\", "/").split("/")
            parent = self.tree.invisibleRootItem()
            for i, part in enumerate(parts[:-1]):
                key = "/".join(parts[:i + 1])
                if key not in folders:
                    folder = QTreeWidgetItem(parent, [part])
                    folder.setIcon(0, folder_icon)
                    folder.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder"})
                    folder.setExpanded(i < 1)
                    folders[key] = folder
                parent = folders[key]
            file_item = QTreeWidgetItem(parent, [parts[-1]])
            file_item.setIcon(0, file_icon)
            file_item.setToolTip(0, f"{fpath} · {fast.total_lines} dòng")
            file_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "file", "path": fpath})
            for sym in fast.symbols:
                total_symbols += 1
                sym_item = QTreeWidgetItem(file_item)
                suffix = "()" if sym.symbol_type == "function" else ""
                sym_item.setText(0, sym.name + suffix)
                sym_item.setForeground(0, QColor("#aebbd2"))
                sym_item.setToolTip(0, f"{sym.symbol_type} · Dòng {sym.start_line}–{sym.end_line}")
                sym_item.setData(0, Qt.ItemDataRole.UserRole, {
                    "type": "symbol", "path": fpath,
                    "start_line": sym.start_line, "end_line": sym.end_line, "name": sym.name
                })
        self.lbl_stats.setText(f"{len(files)} tệp · {total_symbols} symbols")
        if self.file_search.text():
            self.filter_tree(self.file_search.text())

    def filter_tree(self, text: str):
        query = text.strip().lower()

        def visit(item, ancestor_matches=False):
            data = item.data(0, Qt.ItemDataRole.UserRole) or {}
            matches = not query or ancestor_matches or query in item.text(0).lower() or query in data.get("path", "").lower()
            child_matches = [visit(item.child(i), matches) for i in range(item.childCount())]
            visible = matches or any(child_matches)
            item.setHidden(not visible)
            if query and visible and item.childCount():
                item.setExpanded(True)
            return visible

        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            visit(root.child(i))

    def on_tree_item_clicked(self, item: QTreeWidgetItem, col: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("type") == "file":
            self.file_selected.emit(data["path"])

    def on_tree_item_double_clicked(self, item: QTreeWidgetItem, col: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("type") == "symbol":
            self.symbol_selected.emit(data["path"], data["start_line"], data["end_line"])
