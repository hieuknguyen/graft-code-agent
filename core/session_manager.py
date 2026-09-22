import os
import json
import uuid
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

class SessionManager:
    """
    Quản lý lưu trữ Projects và Conversations 100% CỤC BỘ trên máy tính.
    Tuyệt đối không lưu trên máy chủ (server) hoặc cloud.
    Cấu trúc lưu trữ:
      <storage_dir>/
        projects.json
        conversations/
          <project_id>/
            <conv_id>.json
    """

    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir:
            self.storage_dir = Path(storage_dir).resolve()
        else:
            base_dir = Path(__file__).resolve().parent.parent
            self.storage_dir = base_dir / "storage"

        self.projects_file = self.storage_dir / "projects.json"
        self.conversations_dir = self.storage_dir / "conversations"
        self._conv_meta_cache: Dict[str, Any] = {}

        self._ensure_storage_dirs()

    def _ensure_storage_dirs(self):
        """Khởi tạo các thư mục lưu trữ cục bộ nếu chưa tồn tại."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.conversations_dir.mkdir(parents=True, exist_ok=True)
        if not self.projects_file.exists():
            self._save_json(self.projects_file, [])

    def _load_json(self, file_path: Path, default: Any = None) -> Any:
        try:
            if file_path.exists():
                return json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[SessionManager] Lỗi đọc file {file_path}: {e}")
        return default if default is not None else {}

    def _save_json(self, file_path: Path, data: Any):
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[SessionManager] Lỗi ghi file {file_path}: {e}")

    # ==================== PROJECT MANAGEMENT ====================

    def get_projects(self) -> List[Dict[str, Any]]:
        """Lấy danh sách tất cả các dự án đã đăng ký trên máy."""
        projects = self._load_json(self.projects_file, default=[])
        # Sắp xếp theo thời gian cập nhật mới nhất
        projects.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return projects

    def get_or_create_project(self, folder_path: str) -> Dict[str, Any]:
        """Lấy thông tin dự án theo đường dẫn thư mục, nếu chưa có thì tạo mới."""
        abs_path = os.path.abspath(folder_path)
        projects = self.get_projects()

        for p in projects:
            if os.path.abspath(p.get("path", "")) == abs_path:
                # Cập nhật updated_at
                p["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._save_json(self.projects_file, projects)
                return p

        # Tạo project mới
        folder_name = os.path.basename(abs_path) or "Project"
        proj_id = f"proj_{uuid.uuid4().hex[:10]}"
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        new_proj = {
            "id": proj_id,
            "name": folder_name,
            "path": abs_path,
            "created_at": now_str,
            "updated_at": now_str
        }

        projects.insert(0, new_proj)
        self._save_json(self.projects_file, projects)

        # Tạo thư mục conversations cho project
        (self.conversations_dir / proj_id).mkdir(parents=True, exist_ok=True)
        return new_proj

    def delete_project(self, project_id: str) -> bool:
        """Xóa dự án và các cuộc trò chuyện liên quan khỏi máy."""
        projects = self.get_projects()
        filtered = [p for p in projects if p.get("id") != project_id]
        if len(filtered) != len(projects):
            self._save_json(self.projects_file, filtered)
            # Xóa thư mục conversations của project
            conv_folder = self.conversations_dir / project_id
            if conv_folder.exists():
                import shutil
                shutil.rmtree(conv_folder, ignore_errors=True)
            # Xóa cache liên quan đến project
            conv_folder_str = str(conv_folder.resolve())
            self._conv_meta_cache = {
                k: v for k, v in self._conv_meta_cache.items()
                if not k.startswith(conv_folder_str)
            }
            return True
        return False

    # ==================== CONVERSATION MANAGEMENT ====================

    def get_conversations(self, project_id: str) -> List[Dict[str, Any]]:
        """Lấy danh sách các cuộc trò chuyện của một dự án (chỉ metadata, có bộ nhớ đệm mtime)."""
        conv_folder = self.conversations_dir / project_id
        if not conv_folder.exists():
            return []

        conv_list = []
        for file in conv_folder.glob("*.json"):
            file_key = str(file.resolve())
            try:
                mtime = file.stat().st_mtime
            except OSError:
                mtime = 0

            cached = self._conv_meta_cache.get(file_key)
            if cached and cached[0] == mtime:
                conv_list.append(dict(cached[1]))
                continue

            data = self._load_json(file)
            if data and "id" in data:
                meta = {
                    "id": data.get("id"),
                    "project_id": project_id,
                    "title": data.get("title", "Cuộc trò chuyện"),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "message_count": len(data.get("messages", []))
                }
                self._conv_meta_cache[file_key] = (mtime, meta)
                conv_list.append(dict(meta))

        # Sắp xếp mới nhất lên đầu
        conv_list.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return conv_list

    def create_conversation(self, project_id: str, title: str = "Cuộc trò chuyện mới") -> Dict[str, Any]:
        """Tạo một cuộc trò chuyện hoàn toàn mới, riêng biệt cho dự án."""
        conv_id = f"conv_{uuid.uuid4().hex[:12]}"
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conv_data = {
            "id": conv_id,
            "project_id": project_id,
            "title": title,
            "created_at": now_str,
            "updated_at": now_str,
            "messages": []
        }

        file_path = self.conversations_dir / project_id / f"{conv_id}.json"
        self._save_json(file_path, conv_data)
        file_key = str(file_path.resolve())
        try:
            mtime = file_path.stat().st_mtime
        except OSError:
            mtime = 0
        self._conv_meta_cache[file_key] = (mtime, {
            "id": conv_id,
            "project_id": project_id,
            "title": title,
            "created_at": now_str,
            "updated_at": now_str,
            "message_count": 0
        })

        # Cập nhật updated_at của project
        projects = self.get_projects()
        for p in projects:
            if p.get("id") == project_id:
                p["updated_at"] = now_str
                break
        self._save_json(self.projects_file, projects)

        return conv_data

    def get_conversation(self, project_id: str, conv_id: str) -> Optional[Dict[str, Any]]:
        """Lấy chi tiết toàn bộ nội dung (bao gồm messages) của một cuộc trò chuyện."""
        file_path = self.conversations_dir / project_id / f"{conv_id}.json"
        if file_path.exists():
            return self._load_json(file_path)
        return None

    def save_conversation(self, project_id: str, conv_id: str, conv_data: Dict[str, Any]):
        """Lưu đè dữ liệu của một cuộc trò chuyện xuống đĩa."""
        conv_data["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file_path = self.conversations_dir / project_id / f"{conv_id}.json"
        self._save_json(file_path, conv_data)
        file_key = str(file_path.resolve())
        try:
            mtime = file_path.stat().st_mtime
        except OSError:
            mtime = 0
        self._conv_meta_cache[file_key] = (mtime, {
            "id": conv_data.get("id", conv_id),
            "project_id": project_id,
            "title": conv_data.get("title", "Cuộc trò chuyện"),
            "created_at": conv_data.get("created_at", ""),
            "updated_at": conv_data.get("updated_at", ""),
            "message_count": len(conv_data.get("messages", []))
        })

    def append_message(self, project_id: str, conv_id: str, message: Dict[str, Any]):
        """Thêm 1 tin nhắn vào cuộc trò chuyện và lưu ngay xuống đĩa."""
        conv = self.get_conversation(project_id, conv_id)
        if conv is None:
            conv = self.create_conversation(project_id)
            conv_id = conv["id"]

        if "timestamp" not in message:
            message["timestamp"] = datetime.datetime.now().strftime("%H:%M")

        conv["messages"].append(message)
        conv["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Nếu title vẫn là mặc định và tin nhắn là của user, tự động đặt tên theo câu hỏi đầu tiên
        if conv.get("title") in ("Cuộc trò chuyện mới", "Hội thoại mới", "") and message.get("role") == "user":
            txt = message.get("text", "").strip()
            if txt:
                first_line = txt.splitlines()[0][:36]
                conv["title"] = first_line

        self.save_conversation(project_id, conv_id, conv)

    def rename_conversation(self, project_id: str, conv_id: str, new_title: str) -> bool:
        """Đổi tên cuộc trò chuyện."""
        conv = self.get_conversation(project_id, conv_id)
        if conv:
            conv["title"] = new_title.strip() or "Cuộc trò chuyện"
            conv["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save_conversation(project_id, conv_id, conv)
            return True
        return False

    def delete_conversation(self, project_id: str, conv_id: str) -> bool:
        """Xóa vĩnh viễn file cuộc trò chuyện khỏi đĩa cứng."""
        file_path = self.conversations_dir / project_id / f"{conv_id}.json"
        self._conv_meta_cache.pop(str(file_path.resolve()), None)
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def delete_message(self, project_id: str, conv_id: str, message_index: int) -> bool:
        """Xóa 1 tin nhắn tại vị trí message_index khỏi cuộc trò chuyện."""
        conv = self.get_conversation(project_id, conv_id)
        if conv and "messages" in conv:
            if 0 <= message_index < len(conv["messages"]):
                del conv["messages"][message_index]
                self.save_conversation(project_id, conv_id, conv)
                return True
        return False

    def clear_conversation_messages(self, project_id: str, conv_id: str) -> bool:
        """Xóa sạch tin nhắn trong cuộc trò chuyện nhưng vẫn giữ metadata."""
        conv = self.get_conversation(project_id, conv_id)
        if conv:
            conv["messages"] = []
            self.save_conversation(project_id, conv_id, conv)
            return True
        return False
