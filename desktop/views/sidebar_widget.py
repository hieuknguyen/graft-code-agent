import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QFileDialog, QComboBox,
    QTabWidget, QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
    QMenu, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QIcon, QFont, QAction, QColor

from desktop.icons import icon

from core.agent import GraftAgent
from core.session_manager import SessionManager

class SidebarWidget(QWidget):
    project_switched = Signal(str) # folder_path
    conversation_selected = Signal(str) # conv_id
    new_conversation_requested = Signal()
    rename_conversation_requested = Signal(str, str) # conv_id, new_title
    delete_conversation_requested = Signal(str) # conv_id

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
        self.setMinimumWidth(210)
        self.setMaximumWidth(420)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 9, 10, 8)
        main_layout.setSpacing(10)
        title_row = QHBoxLayout()
        title = QLabel("WORKSPACE")
        title.setObjectName("sectionLabel")
        title_row.addWidget(title)
        title_row.addStretch()
        for attr, name, tooltip, signal in (
            ("btn_rescan", "refresh", "Quét lại codebase (F5)", self.rescan_requested),
            ("btn_doctor", "activity", "Kiểm tra môi trường (F6)", self.doctor_requested),
        ):
            button = QPushButton(icon(name), "")
            button.setObjectName("iconButton")
            button.setFixedSize(26, 26)
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
            button.clicked.connect(signal.emit)
            setattr(self, attr, button)
            title_row.addWidget(button)
        main_layout.addLayout(title_row)
        self.project_combo = QComboBox()
        self.project_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.project_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.project_combo.setMinimumContentsLength(10)
        self.project_combo.setToolTip("Chọn dự án làm việc")
        self.project_combo.currentIndexChanged.connect(self.on_project_combo_changed)
        main_layout.addWidget(self.project_combo)
        self.btn_import = QPushButton(icon("folder"), "Mở thư mục…")
        self.btn_import.setToolTip("Mở dự án từ máy tính (Ctrl+O)")
        self.btn_import.clicked.connect(self.browse_folder)
        main_layout.addWidget(self.btn_import)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)
        tab_convs = QWidget()
        conv_layout = QVBoxLayout(tab_convs)
        conv_layout.setContentsMargins(0, 10, 0, 0)
        conv_layout.setSpacing(8)
        self.btn_new_chat = QPushButton(icon("plus"), "Cuộc trò chuyện mới")
        self.btn_new_chat.clicked.connect(self.new_conversation_requested.emit)
        conv_layout.addWidget(self.btn_new_chat)
        self.conv_search = QLineEdit()
        self.conv_search.setObjectName("sidebarSearch")
        self.conv_search.setPlaceholderText("Tìm cuộc trò chuyện…")
        self.conv_search.textChanged.connect(self.filter_conversations)
        conv_layout.addWidget(self.conv_search)
        self.conv_list = QListWidget()
        self.conv_list.setWordWrap(True)
        self.conv_list.itemClicked.connect(self.on_conv_item_clicked)
        self.conv_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.conv_list.customContextMenuRequested.connect(self.show_conv_context_menu)
        conv_layout.addWidget(self.conv_list)
        self.lbl_storage_info = QLabel("Lịch sử được lưu trên máy")
        self.lbl_storage_info.setObjectName("muted")
        conv_layout.addWidget(self.lbl_storage_info)
        self.tabs.addTab(tab_convs, "Lịch sử")

        tab_files = QWidget()
        files_layout = QVBoxLayout(tab_files)
        files_layout.setContentsMargins(0, 10, 0, 0)
        files_layout.setSpacing(8)
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
        self.tabs.addTab(tab_files, "Explorer")
        self.tabs.setCurrentIndex(1)
        main_layout.addWidget(self.tabs)

    # ==================== PROJECT ACTIONS ====================

    def reload_projects_list(self, active_path: str):
        """Nạp lại danh sách dự án vào combobox và chọn active_path."""
        self.project_combo.blockSignals(True)
        self.project_combo.clear()

        projects = self.session_mgr.get_projects()
        current_idx = 0

        abs_active = os.path.abspath(active_path)
        for i, p in enumerate(projects):
            p_path = p.get("path", "")
            p_name = p.get("name", "Project")
            self.project_combo.addItem(icon("folder"), p_name, p_path)
            self.project_combo.setItemData(i, p_path, Qt.ItemDataRole.ToolTipRole)
            if os.path.abspath(p_path) == abs_active:
                current_idx = i

        self.project_combo.setCurrentIndex(current_idx)
        self.project_combo.blockSignals(False)

    def on_project_combo_changed(self, index: int):
        folder = self.project_combo.itemData(index)
        if folder and str(self.agent.root_dir) != folder:
            self.project_switched.emit(folder)

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
            c_id = c["id"]
            title = c.get("title", "Cuộc trò chuyện mới")
            updated_at = c.get("updated_at", "")
            time_str = updated_at[11:16] if len(updated_at) >= 16 else ""
            date_str = updated_at[5:10] if len(updated_at) >= 10 else ""

            item = QListWidgetItem(self.conv_list)
            item.setText(f"{title}\n{date_str} · {time_str} · {c.get('message_count', 0)} tin nhắn")
            item.setToolTip(title)
            item.setData(Qt.ItemDataRole.UserRole, c)

            if select_conv_id and c_id == select_conv_id:
                selected_item = item
            elif selected_item is None:
                selected_item = item

        if selected_item:
            self.conv_list.setCurrentItem(selected_item)
            c_data = selected_item.data(Qt.ItemDataRole.UserRole)
            self.current_conv_id = c_data["id"]
        else:
            self.current_conv_id = None
        self.filter_conversations(self.conv_search.text())

    def on_conv_item_clicked(self, item: QListWidgetItem):
        c_data = item.data(Qt.ItemDataRole.UserRole)
        if c_data:
            c_id = c_data["id"]
            self.current_conv_id = c_id
            self.conversation_selected.emit(c_id)

    def filter_conversations(self, query: str):
        q = query.strip().lower()
        for i in range(self.conv_list.count()):
            item = self.conv_list.item(i)
            c_data = item.data(Qt.ItemDataRole.UserRole)
            title = c_data.get("title", "").lower() if c_data else ""
            item.setHidden(bool(q and q not in title))

    def show_conv_context_menu(self, pos: QPoint):
        item = self.conv_list.itemAt(pos)
        if not item:
            return

        c_data = item.data(Qt.ItemDataRole.UserRole)
        c_id = c_data["id"]
        c_title = c_data.get("title", "Cuộc trò chuyện")

        menu = QMenu(self)
        act_rename = menu.addAction("✏️ Đổi Tên Hội Thoại")
        act_delete = menu.addAction("🗑️ Xóa Hội Thoại Này")

        action = menu.exec(self.conv_list.mapToGlobal(pos))
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
