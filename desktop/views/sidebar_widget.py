import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QFileDialog, QComboBox,
    QTabWidget, QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
    QMenu
)
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QIcon, QFont, QAction, QColor

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
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # 1. HEADER: Project Selection
        header_box = QVBoxLayout()
        header_box.setSpacing(4)

        title_row = QHBoxLayout()
        title_icon = QLabel("🏢")
        title_icon.setStyleSheet("font-size: 15px;")
        title_row.addWidget(title_icon)

        title_lbl = QLabel("QUẢN LÝ PROJECT & CHAT")
        title_lbl.setStyleSheet("font-weight: bold; color: #818cf8; font-size: 11px; letter-spacing: 0.5px;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        self.btn_rescan = QPushButton("🔄")
        self.btn_rescan.setToolTip("Quét lại cấu trúc AST codebase")
        self.btn_rescan.setFixedWidth(28)
        self.btn_rescan.clicked.connect(self.rescan_requested.emit)
        title_row.addWidget(self.btn_rescan)

        self.btn_doctor = QPushButton("🩺")
        self.btn_doctor.setToolTip("Chẩn đoán môi trường & thư viện (Doctor)")
        self.btn_doctor.setFixedWidth(28)
        self.btn_doctor.clicked.connect(self.doctor_requested.emit)
        title_row.addWidget(self.btn_doctor)
        header_box.addLayout(title_row)

        # Project Selector Combobox
        self.project_combo = QComboBox()
        self.project_combo.setToolTip("Chọn dự án làm việc")
        self.project_combo.currentIndexChanged.connect(self.on_project_combo_changed)
        header_box.addWidget(self.project_combo)

        # Buttons: Import Project
        proj_btn_row = QHBoxLayout()
        self.btn_import = QPushButton("📂 Import Project Mới...")
        self.btn_import.setObjectName("primaryButton")
        self.btn_import.setStyleSheet("padding: 6px 10px; font-weight: bold; font-size: 11px;")
        self.btn_import.clicked.connect(self.browse_folder)
        proj_btn_row.addWidget(self.btn_import)

        self.btn_doc_quick = QPushButton("🩺 Doctor")
        self.btn_doc_quick.setStyleSheet("padding: 6px 10px; font-weight: bold; font-size: 11px; background-color: #0f766e; color: #ccfbf1; border: 1px solid #14b8a6;")
        self.btn_doc_quick.clicked.connect(self.doctor_requested.emit)
        proj_btn_row.addWidget(self.btn_doc_quick)
        header_box.addLayout(proj_btn_row)

        main_layout.addLayout(header_box)

        # 2. TABS: Tab 1 (Conversations - MẶC ĐỊNH), Tab 2 (Files & AST)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #1e293b; background: #070a13; border-radius: 6px; }
            QTabBar::tab { background: #0f172a; color: #94a3b8; padding: 6px 10px; border-top-left-radius: 4px; border-top-right-radius: 4px; font-weight: bold; font-size: 11px; }
            QTabBar::tab:selected { background: #1e293b; color: #38bdf8; border-bottom: 2px solid #38bdf8; }
        """)

        # --- TAB 1: CONVERSATIONS ---
        tab_convs = QWidget()
        conv_layout = QVBoxLayout(tab_convs)
        conv_layout.setContentsMargins(4, 6, 4, 4)
        conv_layout.setSpacing(6)

        # Button: New Conversation
        self.btn_new_chat = QPushButton("➕ Cuộc Trò Chuyện Mới")
        self.btn_new_chat.setStyleSheet("""
            QPushButton {
                background-color: #4f46e5;
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
                padding: 8px 12px;
                border-radius: 6px;
                border: 1px solid #6366f1;
            }
            QPushButton:hover {
                background-color: #4338ca;
            }
        """)
        self.btn_new_chat.clicked.connect(self.new_conversation_requested.emit)
        conv_layout.addWidget(self.btn_new_chat)

        # Search Conversations
        self.conv_search = QLineEdit()
        self.conv_search.setPlaceholderText("🔍 Tìm cuộc trò chuyện...")
        self.conv_search.setStyleSheet("padding: 4px 8px; font-size: 11px;")
        self.conv_search.textChanged.connect(self.filter_conversations)
        conv_layout.addWidget(self.conv_search)

        # Conversations List
        self.conv_list = QListWidget()
        self.conv_list.setStyleSheet("""
            QListWidget {
                background-color: #050811;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 4px;
            }
            QListWidget::item {
                background-color: #0d1322;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 8px 10px;
                margin-bottom: 4px;
                color: #e2e8f0;
            }
            QListWidget::item:hover {
                background-color: #1e1b4b;
                border: 1px solid #4338ca;
            }
            QListWidget::item:selected {
                background-color: #1e1b4b;
                border: 1px solid #6366f1;
                color: #ffffff;
            }
        """)
        self.conv_list.itemClicked.connect(self.on_conv_item_clicked)
        self.conv_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.conv_list.customContextMenuRequested.connect(self.show_conv_context_menu)
        conv_layout.addWidget(self.conv_list)

        # Storage indicator label
        self.lbl_storage_info = QLabel("🔒 100% Cục bộ trên máy tính (Local Disk)")
        self.lbl_storage_info.setStyleSheet("color: #64748b; font-size: 10px; padding: 2px;")
        self.lbl_storage_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        conv_layout.addWidget(self.lbl_storage_info)

        self.tabs.addTab(tab_convs, "💬 Hội Thoại")

        # --- TAB 2: FILES & AST SYMBOLS ---
        tab_files = QWidget()
        files_layout = QVBoxLayout(tab_files)
        files_layout.setContentsMargins(4, 6, 4, 4)
        files_layout.setSpacing(6)

        self.file_search = QLineEdit()
        self.file_search.setPlaceholderText("🔍 Lọc hàm, class, tệp...")
        self.file_search.setStyleSheet("padding: 4px 8px; font-size: 11px;")
        self.file_search.textChanged.connect(self.filter_tree)
        files_layout.addWidget(self.file_search)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Tên File / Biểu tượng AST", "Dòng"])
        self.tree.setColumnWidth(0, 190)
        self.tree.setStyleSheet("""
            QTreeWidget {
                background-color: #050811;
                border: 1px solid #1e293b;
                border-radius: 6px;
            }
        """)
        self.tree.itemClicked.connect(self.on_tree_item_clicked)
        self.tree.itemDoubleClicked.connect(self.on_tree_item_double_clicked)
        files_layout.addWidget(self.tree)

        self.lbl_stats = QLabel("0 tệp | 0 biểu tượng AST")
        self.lbl_stats.setStyleSheet("color: #64748b; font-size: 10px;")
        files_layout.addWidget(self.lbl_stats)

        self.tabs.addTab(tab_files, "📁 Cây Tệp & AST")

        main_layout.addWidget(self.tabs)

        # Set default tab to Conversations
        self.tabs.setCurrentIndex(0)

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
            self.project_combo.addItem(f"📁 {p_name} ({p_path})", p_path)
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
            item.setText(f"💬  {title}\n🕒 {time_str} ({date_str}) • {c.get('message_count', 0)} tin nhắn")
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

        for fpath, fast in sorted(files.items()):
            file_item = QTreeWidgetItem(self.tree)
            file_item.setText(0, f"📄 {fpath}")
            file_item.setText(1, f"{fast.total_lines} dòng")
            file_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "file", "path": fpath})
            file_item.setFont(0, QFont("Segoe UI", 9, QFont.Weight.Bold))

            for sym in fast.symbols:
                total_symbols += 1
                sym_item = QTreeWidgetItem(file_item)
                prefix = "⚡" if sym.symbol_type == "function" else ("🏛️" if sym.symbol_type == "class" else "🔹")
                args_str = f"({', '.join(sym.args)})" if sym.args else ""
                sym_item.setText(0, f"{prefix} {sym.name}{args_str}")
                sym_item.setText(1, f"L{sym.start_line}-{sym.end_line}")
                sym_item.setData(0, Qt.ItemDataRole.UserRole, {
                    "type": "symbol",
                    "path": fpath,
                    "start_line": sym.start_line,
                    "end_line": sym.end_line,
                    "name": sym.name
                })
            file_item.setExpanded(True)

        self.lbl_stats.setText(f"{len(files)} tệp mã nguồn | {total_symbols} biểu tượng AST")

    def filter_tree(self, text: str):
        query = text.strip().lower()
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            file_item = root.child(i)
            file_match = query in file_item.text(0).lower()
            visible_children = 0
            for j in range(file_item.childCount()):
                sym_item = file_item.child(j)
                sym_match = query in sym_item.text(0).lower()
                sym_item.setHidden(not sym_match and not file_match)
                if sym_match or file_match:
                    visible_children += 1
            file_item.setHidden(visible_children == 0 and not file_match)
            if visible_children > 0:
                file_item.setExpanded(True)

    def on_tree_item_clicked(self, item: QTreeWidgetItem, col: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("type") == "file":
            self.file_selected.emit(data["path"])

    def on_tree_item_double_clicked(self, item: QTreeWidgetItem, col: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("type") == "symbol":
            self.symbol_selected.emit(data["path"], data["start_line"], data["end_line"])
