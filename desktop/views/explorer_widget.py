import os
from pathlib import Path
from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QFileDialog, QComboBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QFont
from core.agent import GraftAgent

class ExplorerWidget(QWidget):
    folder_changed = Signal(str)
    file_selected = Signal(str)
    symbol_selected = Signal(str, int, int) # file, start_line, end_line
    doctor_requested = Signal()

    def __init__(self, agent: GraftAgent, parent=None):
        super().__init__(parent)
        self.agent = agent
        self.recent_folders: List[str] = [str(self.agent.root_dir)]
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header Title
        title_box = QHBoxLayout()
        icon_lbl = QLabel("📂")
        icon_lbl.setStyleSheet("font-size: 16px;")
        title_box.addWidget(icon_lbl)

        title_lbl = QLabel("DỰ ÁN HIỆN TẠI")
        title_lbl.setStyleSheet("font-weight: bold; color: #818cf8; font-size: 12px; letter-spacing: 0.5px;")
        title_box.addWidget(title_lbl)
        title_box.addStretch()

        self.btn_rescan = QPushButton("🔄")
        self.btn_rescan.setToolTip("Quét lại cấu trúc AST codebase")
        self.btn_rescan.setFixedWidth(32)
        title_box.addWidget(self.btn_rescan)

        self.btn_doctor = QPushButton("🩺")
        self.btn_doctor.setToolTip("Chẩn đoán môi trường máy tính & thư viện dự án (Doctor)")
        self.btn_doctor.setFixedWidth(32)
        self.btn_doctor.clicked.connect(self.doctor_requested.emit)
        title_box.addWidget(self.btn_doctor)
        layout.addLayout(title_box)

        # Action Buttons: Import Folder & Doctor
        btn_row = QHBoxLayout()
        self.btn_import = QPushButton("📂 Import Folder...")
        self.btn_import.setObjectName("primaryButton")
        self.btn_import.setStyleSheet("padding: 8px 10px; font-weight: bold;")
        self.btn_import.clicked.connect(self.browse_folder)
        btn_row.addWidget(self.btn_import)

        self.btn_check = QPushButton("🩺 Doctor")
        self.btn_check.setStyleSheet("padding: 8px 10px; font-weight: bold; background-color: #0f766e; color: #ccfbf1; border: 1px solid #14b8a6;")
        self.btn_check.setToolTip("Kiểm tra xem máy tính và dự án đã sẵn sàng hay thiếu gì")
        self.btn_check.clicked.connect(self.doctor_requested.emit)
        btn_row.addWidget(self.btn_check)
        layout.addLayout(btn_row)

        # Current Folder Label & Recent Switcher
        self.folder_combo = QComboBox()
        self.folder_combo.setToolTip("Chọn thư mục đã làm việc gần đây")
        self.folder_combo.addItem(f"📁 {os.path.basename(str(self.agent.root_dir))} ({self.agent.root_dir})", str(self.agent.root_dir))
        self.folder_combo.currentIndexChanged.connect(self.on_recent_selected)
        layout.addWidget(self.folder_combo)

        # Search / Filter Box
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 Lọc hàm, class, tệp...")
        self.search_edit.textChanged.connect(self.filter_tree)
        layout.addWidget(self.search_edit)

        # Tree Widget for Files & AST Symbols
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Tên File / Biểu tượng AST", "Dòng"])
        self.tree.setColumnWidth(0, 220)
        self.tree.itemClicked.connect(self.on_item_clicked)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.tree)

        # Stats bar
        self.lbl_stats = QLabel("0 tệp | 0 biểu tượng")
        self.lbl_stats.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(self.lbl_stats)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Chọn thư mục dự án cần cấy ghép code",
            str(self.agent.root_dir)
        )
        if folder:
            self.set_workspace(folder)

    def set_workspace(self, folder_path: str):
        folder_path = os.path.abspath(folder_path)
        if folder_path not in self.recent_folders:
            self.recent_folders.insert(0, folder_path)
            self.folder_combo.insertItem(0, f"📁 {os.path.basename(folder_path)} ({folder_path})", folder_path)
        self.folder_combo.blockSignals(True)
        self.folder_combo.setCurrentIndex(self.recent_folders.index(folder_path))
        self.folder_combo.blockSignals(False)
        self.folder_changed.emit(folder_path)

    def on_recent_selected(self, index: int):
        folder = self.folder_combo.itemData(index)
        if folder and str(self.agent.root_dir) != folder:
            self.folder_changed.emit(folder)

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

    def on_item_clicked(self, item: QTreeWidgetItem, col: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        if data["type"] == "file":
            self.file_selected.emit(data["path"])
        elif data["type"] == "symbol":
            self.symbol_selected.emit(data["path"], data["start_line"], data["end_line"])

    def on_item_double_clicked(self, item: QTreeWidgetItem, col: int):
        self.on_item_clicked(item, col)
